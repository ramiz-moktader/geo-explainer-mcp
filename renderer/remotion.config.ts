import os from "os";
import { Config } from "@remotion/cli/config";

// MapLibre needs WebGL. Headless Linux boxes usually have no GPU, so default to
// the software renderer there; override with GEO_GL=angle|egl|swiftshader|vulkan.
const gl = (process.env.GEO_GL ??
  (os.platform() === "linux" ? "swangle" : "angle")) as
  | "swangle"
  | "angle"
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
