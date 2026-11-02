<?php
declare(strict_types=1);

final class Db
{
    private static ?PDO $pdo = null;

    public static function pdo(): PDO
    {
        if (self::$pdo === null) {
            $url = env('DATABASE_URL');
            if (!$url) {
                throw new RuntimeException('DATABASE_URL is required (the web app shares the bot Postgres DB).');
            }
            $p = parse_url($url);
            if (!$p || empty($p['host'])) {
                throw new RuntimeException('DATABASE_URL is malformed.');
            }
            $dsn = sprintf(
                'pgsql:host=%s;port=%d;dbname=%s;sslmode=%s',
                $p['host'],
                $p['port'] ?? 5432,
                ltrim($p['path'] ?? '/postgres', '/'),
                str_contains($url, 'supabase') ? 'require' : 'prefer'
            );
            self::$pdo = new PDO($dsn, urldecode($p['user'] ?? ''), urldecode($p['pass'] ?? ''), [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            ]);
            self::$pdo->exec("SET TIME ZONE 'UTC'");
        }
        return self::$pdo;
    }
}
