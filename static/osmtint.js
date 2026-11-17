/* Camadas OSM recoloridas no navegador (canvas):
 *  - osmTint('base'):  cinza em tudo, ruas/avenidas/rodovias em tons de azul (por categoria)
 *  - osmTint('nomes'): só os textos (nomes de cidades/rodovias), transparente no resto,
 *                      para ficar ACIMA da rota (o OSM traz os nomes dentro da imagem)
 * Cores de rua do OpenStreetMap padrão -> azul. */
(function () {
  const URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  // [cor original (preenchimento ou contorno), cor nova]
  const ROADS = [
    [[232, 146, 162], [24, 62, 196]],  [[220, 42, 103], [18, 44, 150]],    // rodovia (motorway)
    [[249, 178, 156], [37, 99, 235]],  [[200, 78, 47], [26, 70, 180]],     // tronco (trunk)
    [[252, 214, 164], [66, 133, 244]], [[160, 107, 0], [37, 99, 235]],     // primária
    [[247, 250, 191, 11], [125, 183, 250]], [[112, 125, 5], [66, 133, 244]]    // secundária
  ];
  const TOL = 24;

  const Layer = L.GridLayer.extend({
    initialize(mode, opts) { this._mode = mode; L.GridLayer.prototype.initialize.call(this, opts); },
    createTile(coords, done) {
      const tile = L.DomUtil.create('canvas', 'leaflet-tile');
      const size = this.getTileSize(); tile.width = size.x; tile.height = size.y;
      const n = 2 ** coords.z, x = ((coords.x % n) + n) % n;
      if (coords.y < 0 || coords.y >= n) { done(null, tile); return tile; }
      const img = new Image(); img.crossOrigin = 'anonymous';
      img.onload = () => {
        const ctx = tile.getContext('2d', {willReadFrequently: true});
        ctx.drawImage(img, 0, 0, size.x, size.y);
        const im = ctx.getImageData(0, 0, size.x, size.y), d = im.data;
        for (let i = 0; i < d.length; i += 4) {
          const r = d[i], g = d[i + 1], b = d[i + 2], lum = .3 * r + .59 * g + .11 * b;
          if (this._mode === 'nomes') {
            // mantém só pixels escuros (texto); o resto fica transparente
            const a = lum < 95 ? 255 : lum < 150 ? Math.round((150 - lum) / 55 * 255) : 0;
            d[i] = d[i + 1] = d[i + 2] = 40; d[i + 3] = a; continue;
          }
          let hit = null;
          for (const [o, nw] of ROADS) {
            const dr = r - o[0], dg = g - o[1], db = b - o[2];
            const tol = o[3] || TOL;
            if (dr * dr + dg * dg + db * db < tol * tol) { hit = nw; break; }
          }
          if (hit) { d[i] = hit[0]; d[i + 1] = hit[1]; d[i + 2] = hit[2]; continue; }
          const v = Math.min(255, lum * 1.04 + 6);   // restante: cinza suave
          d[i] = d[i + 1] = d[i + 2] = v;
        }
        ctx.putImageData(im, 0, 0);
        done(null, tile);
      };
      img.onerror = () => done(null, tile);
      img.src = L.Util.template(URL, {z: coords.z, x, y: coords.y});
      return tile;
    }
  });
  window.osmTint = (mode, opts) => new Layer(mode, Object.assign({tileSize: 256, maxZoom: 19}, opts));
})();
