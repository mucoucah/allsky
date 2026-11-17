import { liveApi } from "./live";
import { tonightApi } from "./tonight";
import { archiveApi } from "./archive";
import { cameraApi } from "./camera";
import { systemApi } from "./system";
import { extrasApi } from "./extras";

export { ApiError, fileUrl } from "./client";
export * from "./types";

export const api = {
  ...liveApi,
  ...tonightApi,
  ...archiveApi,
  ...cameraApi,
  ...systemApi,
  ...extrasApi,
};
