/**
 * Minimal implementation of the Streamlit custom-component iframe protocol.
 *
 * Replaces the streamlit-component-lib npm package so the frontend needs no
 * build step. The protocol is a small set of postMessage messages:
 *
 *   iframe -> app:  streamlit:componentReady, streamlit:setComponentValue,
 *                   streamlit:setFrameHeight
 *   app -> iframe:  streamlit:render  (carries args from Python)
 */

"use strict";

const StreamlitProtocol = {
  /** Send a message to the Streamlit app. */
  _send(type, data) {
    window.parent.postMessage(
      Object.assign({ isStreamlitMessage: true, type: type }, data),
      "*"
    );
  },

  /** Tell Streamlit the component is ready to receive render events. */
  ready() {
    this._send("streamlit:componentReady", { apiVersion: 1 });
  },

  /** Report the iframe's desired height (we keep it at 0: invisible). */
  setFrameHeight(height) {
    this._send("streamlit:setFrameHeight", { height: height });
  },

  /** Send a JSON-serializable value back to Python. Triggers a rerun. */
  setComponentValue(value) {
    this._send("streamlit:setComponentValue", { value: value, dataType: "json" });
  },

  /**
   * Register the render handler. `callback(args)` is invoked every time
   * Python (re)runs the component with new arguments.
   */
  onRender(callback) {
    window.addEventListener("message", function (event) {
      const data = event.data;
      if (!data || data.type !== "streamlit:render") return;
      callback(data.args || {});
    });
  },
};
