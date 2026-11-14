import os from "os";
import { Config } from "@remotion/cli/config";

// MapLibre needs WebGL. Headless Linux boxes usually have no GPU, so default to
// the software renderer there; override with GEO_GL=angle|angle-egl|egl|swiftshader|vulkan.
// On a Linux machine with an NVIDIA GPU: GEO_GL=angle-egl GEO_CHROME_MODE=chrome-for-testing
const gl = (process.env.GEO_GL ??
  (os.platform() === "linux" ? "swangle" : "angle")) as
  | "swangle"
  | "angle"
  | "angle-egl"
  | "egl"
  | "swiftshader"
  | "vulkan";

Config.setChromiumOpenGlRenderer(gl);
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(92);
Config.setOverwriteOutput(true);
Config.setDelayRenderTimeoutInMilliseconds(120000);

if (process.env.GEO_BROWSER_EXECUTABLE) {
  Config.setBrowserExecutable(process.env.GEO_BROWSER_EXECUTABLE);
}

// Full Chrome ("chrome-for-testing") can use a GPU on Linux; the default headless shell cannot.
if (process.env.GEO_CHROME_MODE) {
  Config.setChromeMode(process.env.GEO_CHROME_MODE as "headless-shell" | "chrome-for-testing");
}
