/**
 * Browser / display information. Zoom is estimated from the ratio of the window's outer
 * width (device-independent pixels) to its inner width (CSS pixels): at 100% zoom the two
 * are equal, at 125% the ratio is 1.25, etc. This works in desktop Chrome, Firefox and Edge.
 * (Opening the developer tools docked to the side also changes the ratio.)
 */
export function zoomPercent() {
  const ratio = window.outerWidth / window.innerWidth;
  return Number.isFinite(ratio) && ratio > 0 ? Math.round(ratio * 100) : null;
}

export function browserInfo() {
  return {
    zoomPercent: zoomPercent(),
    devicePixelRatio: window.devicePixelRatio,
    screenWidth: window.screen.width,
    screenHeight: window.screen.height,
    windowInnerWidth: window.innerWidth,
    windowInnerHeight: window.innerHeight,
  };
}
