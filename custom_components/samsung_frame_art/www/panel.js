/* Entry point for the Home Assistant custom panel.
 *
 * ha-panel-custom loads this module and then creates the element named in the
 * panel config ("samsung-frame-art-panel"). The element embeds the actual
 * gallery UI (a static HTML page) in an iframe so the panel keeps its own
 * scroll context and styles, while requests stay same-origin and authenticated
 * with the Home Assistant session.
 */

class SamsungFrameArtPanel extends HTMLElement {
  connectedCallback() {
    if (this._iframe) {
      return;
    }
    const iframe = document.createElement("iframe");
    iframe.style.cssText = [
      "border: 0",
      "width: 100%",
      "height: 100%",
      "min-height: calc(100vh - var(--header-height, 56px))",
      "display: block",
      "background-color: var(--primary-background-color, #fafafa)",
    ].join("; ");
    iframe.src = "/samsung_frame_art/www/index.html";
    this.appendChild(iframe);
    this._iframe = iframe;
  }

  // Properties pushed by Home Assistant; the embedded app talks to the API
  // directly with session cookies, so nothing needs to be forwarded.
  set hass(value) {
    this._hass = value;
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    this._narrow = value;
  }

  set route(value) {
    this._route = value;
  }
}

customElements.define("samsung-frame-art-panel", SamsungFrameArtPanel);
