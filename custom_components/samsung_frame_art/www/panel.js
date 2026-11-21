/* Entry point for the Home Assistant custom panel.
 *
 * ha-panel-custom loads this module and then creates the element named in the
 * panel config ("samsung-frame-art-panel"). The element embeds the actual
 * gallery UI (a static HTML page) in an iframe so the panel keeps its own
 * scroll context and styles, while requests stay same-origin.
 *
 * The embedded app cannot authenticate itself with cookies (Home Assistant
 * uses bearer tokens), so the panel element forwards the current access
 * token into the iframe via postMessage whenever it changes.
 */

const TARGET_ORIGIN = window.location.origin;

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
    iframe.addEventListener("load", () => this._postToken());
    this.appendChild(iframe);
    this._iframe = iframe;
    this._lastToken = undefined;
  }

  _currentToken() {
    const auth = this._hass && this._hass.auth;
    if (!auth) {
      return undefined;
    }
    return auth.accessToken || (auth.data && auth.data.access_token) || undefined;
  }

  _postToken() {
    if (!this._iframe || !this._iframe.contentWindow) {
      return;
    }
    const token = this._currentToken();
    if (!token || token === this._lastToken) {
      return;
    }
    this._lastToken = token;
    this._iframe.contentWindow.postMessage(
      { type: "samsung_frame_art_auth", access_token: token },
      TARGET_ORIGIN
    );
  }

  // Properties pushed by Home Assistant. The hass object (with the current
  // access token) is forwarded to the iframe.
  set hass(value) {
    this._hass = value;
    this._postToken();
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
