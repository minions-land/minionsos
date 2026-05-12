/**
 * Imperative VR session control for this viz. We don't use @react-three/xr's
 * built-in VRButton because we already provide our own stylized "Enter VR"
 * chip in the top bar. This module wraps startSession/stopSession so the rest
 * of the app can trigger VR without knowing about the XR internals.
 */
import { startSession, stopSession } from "@react-three/xr";

let current: XRSession | null = null;

function attach(session: XRSession | undefined) {
  if (!session) return;
  current = session;
  session.addEventListener("end", () => {
    current = null;
  });
}

export const xrStore = {
  async enterVR() {
    if (current) {
      await stopSession().catch(() => {});
      current = null;
      return;
    }
    try {
      const session = await startSession("immersive-vr", {
        optionalFeatures: ["local-floor", "bounded-floor", "hand-tracking"],
      });
      attach(session);
    } catch (e) {
      console.warn("[xrStore] failed to enter VR:", e);
    }
  },
  async exitVR() {
    await stopSession().catch(() => {});
    current = null;
  },
};
