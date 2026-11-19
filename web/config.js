/* Map background settings. The default needs no account and no API key. */
window.TE_MAP = {
  // OpenStreetMap's own tiles. The dark look is a CSS filter applied in the browser (see "darken").
  tiles: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  darken: true,

  // Optional: a true "Dark Matter" basemap. CARTO's raster tiles need a free key (no account):
  //   https://carto.com/basemaps/apikey/
  // Paste it between the quotes and reload; leave it empty to keep the default above.
  cartoKey: ""
};
