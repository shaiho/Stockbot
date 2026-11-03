<?php
declare(strict_types=1);

/** Quotes: Finnhub for US when a key exists, Yahoo chart API otherwise / for IL (.TA) / for FX. File-cached. */
final class Prices
{
    private const UA = 'Mozilla/5.0 (compatible; StockbotWeb/1.0)';
    private const FALLBACK_FX = 3.7;

    public function __construct(private string $cacheDir, private int $ttl, private ?string $finnhubKey)
    {
    }

    public static function key(string $symbol, string $market): string
    {
        return $market . ':' . strtoupper($symbol);
    }

    public function usdIls(): float
    {
        $q = $this->quotes([['USDILS=X', 'FX']])[self::key('USDILS=X', 'FX')] ?? null;
        return $q ? $q['price'] : self::FALLBACK_FX;
    }

    /**
     * @param list<array{0:string,1:string}> $pairs [symbol, market]
     * @return array<string, array{price:float, prev_close:?float, change_pct:float}|null>
     */
    public function quotes(array $pairs, bool $fresh = false): array
    {
        $out = [];
        $missing = [];
        foreach ($pairs as [$symbol, $market]) {
            $k = self::key($symbol, $market);
            if (array_key_exists($k, $out)) {
                continue;
            }
            $out[$k] = $fresh ? null : $this->cached($k);
            if ($out[$k] === null) {
                $missing[$k] = [strtoupper($symbol), $market];
            }
        }
        if (!$missing) {
            return $out;
        }

        $useFinnhub = (bool) $this->finnhubKey;
        $first = [];
        foreach ($missing as $k => [$symbol, $market]) {
            $first[$k] = $useFinnhub && $market === 'US' ? $this->finnhubUrl($symbol) : $this->yahooUrl($symbol, $market);
        }
        $bodies = $this->multiGet($first);
        $retry = [];
        foreach ($missing as $k => [$symbol, $market]) {
            $viaFinnhub = $useFinnhub && $market === 'US';
            $q = $this->parse($bodies[$k] ?? null, $viaFinnhub);
            if ($q === null && $viaFinnhub) {
                $retry[$k] = $this->yahooUrl($symbol, $market);
            }
            $out[$k] = $q;
        }
        if ($retry) {
            foreach ($this->multiGet($retry) as $k => $body) {
                $out[$k] = $this->parse($body, false);
            }
        }
        foreach ($missing as $k => $_) {
            if ($out[$k] !== null) {
                $this->store($k, $out[$k]);
            } elseif ($fresh) {
                $out[$k] = $this->cached($k, true);
            }
        }
        return $out;
    }

    private function finnhubUrl(string $symbol): string
    {
        return 'https://finnhub.io/api/v1/quote?symbol=' . rawurlencode($symbol) . '&token=' . rawurlencode((string) $this->finnhubKey);
    }

    private function yahooUrl(string $symbol, string $market): string
    {
        if ($market === 'IL' && !str_ends_with($symbol, '.TA')) {
            $symbol .= '.TA';
        }
        return 'https://query1.finance.yahoo.com/v8/finance/chart/' . rawurlencode($symbol) . '?range=1d&interval=1d';
    }

    private function parse(?string $body, bool $finnhub): ?array
    {
        $j = $body ? json_decode($body, true) : null;
        if (!is_array($j)) {
            return null;
        }
        if ($finnhub) {
            $price = (float) ($j['c'] ?? 0);
            if ($price <= 0) {
                return null;
            }
            $prev = (float) ($j['pc'] ?? 0) ?: null;
        } else {
            $meta = $j['chart']['result'][0]['meta'] ?? null;
            $price = (float) ($meta['regularMarketPrice'] ?? 0);
            if (!$meta || $price <= 0) {
                return null;
            }
            $prev = (float) ($meta['previousClose'] ?? $meta['chartPreviousClose'] ?? 0) ?: null;
        }
        return ['price' => $price, 'prev_close' => $prev, 'change_pct' => $prev ? ($price - $prev) / $prev * 100 : 0.0, 'ts' => time()];
    }

    private function cached(string $key, bool $stale = false): ?array
    {
        $f = $this->cacheFile($key);
        if (!is_file($f) || (!$stale && time() - filemtime($f) >= $this->ttl)) {
            return null;
        }
        $q = json_decode((string) file_get_contents($f), true);
        if (!is_array($q)) {
            return null;
        }
        $q['ts'] ??= filemtime($f);
        return $q;
    }

    private function store(string $key, array $quote): void
    {
        if (!is_dir($this->cacheDir) && !@mkdir($this->cacheDir, 0775, true) && !is_dir($this->cacheDir)) {
            return;
        }
        $tmp = tempnam($this->cacheDir, 'q');
        if ($tmp !== false && file_put_contents($tmp, json_encode($quote)) !== false) {
            rename($tmp, $this->cacheFile($key));
        }
    }

    private function cacheFile(string $key): string
    {
        return $this->cacheDir . '/q_' . md5($key) . '.json';
    }

    /** @param array<string,string> $urls @return array<string,?string> */
    private function multiGet(array $urls): array
    {
        $mh = curl_multi_init();
        $handles = [];
        foreach ($urls as $k => $url) {
            $ch = curl_init($url);
            curl_setopt_array($ch, [
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_TIMEOUT => 8,
                CURLOPT_CONNECTTIMEOUT => 4,
                CURLOPT_FOLLOWLOCATION => true,
                CURLOPT_USERAGENT => self::UA,
                CURLOPT_ENCODING => '',
            ]);
            curl_multi_add_handle($mh, $ch);
            $handles[$k] = $ch;
        }
        do {
            $status = curl_multi_exec($mh, $active);
            if ($active) {
                curl_multi_select($mh, 1.0);
            }
        } while ($active && $status === CURLM_OK);

        $out = [];
        foreach ($handles as $k => $ch) {
            $body = curl_multi_getcontent($ch);
            $out[$k] = curl_getinfo($ch, CURLINFO_HTTP_CODE) === 200 && is_string($body) ? $body : null;
            curl_multi_remove_handle($mh, $ch);
            curl_close($ch);
        }
        curl_multi_close($mh);
        return $out;
    }
}
