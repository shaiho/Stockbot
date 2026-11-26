<?php
require __DIR__ . '/src/Prices.php';
$prices = new Prices(__DIR__ . '/cache', 0, null);
$pairs = [['NVDQ','US'],['SPCH','US'],['NVDX','US'],['COTY','US'],['NVD','US'],['TZA','US'],['NFXL','US'],['SNXX','US'],['STI','US'],['SNDQ','US'],['MU','US'],['USDILS=X','FX']];
$q = $prices->quotes($pairs, true);
foreach ($q as $k => $v) {
    printf("%-14s %s\n", $k, $v ? json_encode($v) : 'null');
}
