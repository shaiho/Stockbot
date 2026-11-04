<?php
declare(strict_types=1);

/** Quotes from the Yahoo chart API (US incl. pre/post market, IL as .TA, FX); Finnhub is the US fallback. File-cached. */
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

        $first = [];
        foreach ($missing as $k => [$symbol, $market]) {
            $first[$k] = $this->yahooUrl($symbol, $market);
        }
        $t0 = microtime(true);
        $bodies = $this->multiGet($first);
        prof_add('quotes', (microtime(true) - $t0) * 1000, count($first));
        $retry = [];
        foreach ($missing as $k => [$symbol, $market]) {
            $out[$k] = $this->parseYahoo($bodies[$k] ?? null, $market === 'US');
            if ($out[$k] === null && $market === 'US' && $this->finnhubKey) {
                $retry[$k] = $this->finnhubUrl($symbol);
            }
        }
        if ($retry) {
            foreach ($this->multiGet($retry) as $k => $body) {
                $out[$k] = $this->parseFinnhub($body);
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
        $url = 'https://query1.finance.yahoo.com/v8/finance/chart/' . rawurlencode($symbol);
        return $market === 'US' ? $url . '?range=1d&interval=1m&includePrePost=true' : $url . '?range=1d&interval=1d';
    }

    private function quote(float $price, ?float $prev, array $extra = []): array
    {
        return ['price' => $price, 'prev_close' => $prev, 'change_pct' => $prev ? ($price - $prev) / $prev * 100 : 0.0, 'ts' => time()] + $extra;
    }

    private function parseFinnhub(?string $body): ?array
    {
        $j = $body ? json_decode($body, true) : null;
        $price = is_array($j) ? (float) ($j['c'] ?? 0) : 0.0;
        return $price > 0 ? $this->quote($price, (float) ($j['pc'] ?? 0) ?: null) : null;
    }

    /**
     * US quotes use the 1-minute series with pre/post market, so the price is the latest trade in any session.
     * Previous close follows the bot: before the regular session opens it is the last regular close.
     */
    private function parseYahoo(?string $body, bool $extended): ?array
    {
        $j = $body ? json_decode($body, true) : null;
        $res = $j['chart']['result'][0] ?? null;
        $meta = $res['meta'] ?? null;
        $regular = (float) ($meta['regularMarketPrice'] ?? 0);
        if (!$meta || $regular <= 0) {
            return null;
        }
        $prev = (float) ($meta['previousClose'] ?? $meta['chartPreviousClose'] ?? 0) ?: null;
        if (!$extended) {
            return $this->quote($regular, $prev);
        }

        $price = $regular;
        foreach (array_reverse($res['indicators']['quote'][0]['close'] ?? []) as $c) {
            if ($c !== null && $c > 0) {
                $price = (float) $c;
                break;
            }
        }
        $now = time();
        $tp = $meta['currentTradingPeriod'] ?? [];
        $in = fn(string $s) => isset($tp[$s]['start'], $tp[$s]['end']) && $now >= $tp[$s]['start'] && $now < $tp[$s]['end'];
        $session = $in('regular') ? 'regular' : ($in('pre') ? 'pre' : ($in('post') ? 'post' : 'closed'));
        if (isset($tp['regular']['start']) && $now < $tp['regular']['start']) {
            $prev = $regular;
        }
        return $this->quote($price, $prev, ['session' => $session, 'regular_price' => $regular]);
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
