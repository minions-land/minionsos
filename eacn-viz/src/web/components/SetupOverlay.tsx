import { useState } from "react";
import { useI18n } from "../i18n";
import { reconnectWithEndpoint } from "../hooks/useStore";

export default function SetupOverlay() {
  const { t, locale, toggleLocale } = useI18n();
  const [endpoint, setEndpoint] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleConnect() {
    const ep = endpoint.trim();
    if (!ep) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${ep}/health`, { signal: AbortSignal.timeout(8000) });
      const data = await res.json();
      if (data?.status === "ok") {
        reconnectWithEndpoint(ep);
        return;
      }
      setError(locale === "en" ? "Endpoint responded but health check failed" : "端点响应正常但健康检查失败");
    } catch {
      setError(
        locale === "en"
          ? "Cannot reach endpoint. Make sure it is HTTPS with CORS enabled."
          : "无法连接端点。请确保使用 HTTPS 并启用 CORS。"
      );
    }
    setLoading(false);
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{
        background: "radial-gradient(circle at top left, rgba(15,118,110,0.1), transparent 34%), radial-gradient(circle at 85% 8%, rgba(223,109,45,0.12), transparent 26%), linear-gradient(180deg, #f9f4ea 0%, #f2ebdf 45%, #f7f2e8 100%)",
      }}
    >
      {/* Grid texture */}
      <div className="fixed inset-0 pointer-events-none" style={{
        backgroundImage: "linear-gradient(rgba(23,23,23,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(23,23,23,0.03) 1px, transparent 1px)",
        backgroundSize: "36px 36px",
        maskImage: "linear-gradient(180deg, rgba(0,0,0,0.16), transparent 70%)",
      }} />

      <div className="relative w-full max-w-lg mx-4">
        {/* Language toggle */}
        <div className="flex justify-end mb-4">
          <button
            onClick={toggleLocale}
            className="flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium border border-[rgba(23,23,23,0.1)] bg-[rgba(255,252,246,0.84)] text-[#5f5a52] hover:text-[#171717] transition-colors"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
              <circle cx="12" cy="12" r="10" />
              <path d="M2 12h20M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10A15 15 0 0 1 12 2z" />
            </svg>
            <span>{locale === "en" ? "中文" : "EN"}</span>
          </button>
        </div>

        {/* Card */}
        <div className="relative border border-[rgba(23,23,23,0.08)] rounded-3xl overflow-hidden"
          style={{
            background: "linear-gradient(180deg, rgba(255,253,249,0.86), rgba(248,240,229,0.92))",
            boxShadow: "0 30px 90px rgba(38,27,11,0.12)",
          }}
        >
          {/* Gradient top stripe */}
          <div className="h-1" style={{
            background: "linear-gradient(90deg, #0f766e, #df6d2d, transparent)",
            opacity: 0.85,
          }} />

          <div className="p-8 space-y-6">
            {/* Brand */}
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl grid place-items-center border border-[rgba(23,23,23,0.08)]" style={{
                background: "linear-gradient(145deg, rgba(15,118,110,0.18), rgba(23,64,102,0.16)), #fff9ef",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.7)",
              }}>
                <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6 text-teal-600">
                  <path d="M5 8.5 12 4l7 4.5v7L12 20l-7-4.5v-7Z" stroke="currentColor" strokeWidth="1.7"/>
                  <path d="M5 8.5 12 13l7-4.5M12 13v7" stroke="currentColor" strokeWidth="1.7"/>
                </svg>
              </div>
              <div>
                <div className="font-mono text-[10px] text-[#0f766e] tracking-[0.12em] uppercase leading-none">Science OS</div>
                <div className="text-lg font-bold text-[#171717] tracking-tight">EACN Viz</div>
              </div>
            </div>

            {/* Title */}
            <div>
              <h2 className="text-xl font-bold text-[#171717] tracking-tight mb-2">
                {t("setup.title")}
              </h2>
              <p className="text-sm text-[#5f5a52] leading-relaxed">
                {t("setup.desc")}
              </p>
            </div>

            {/* Input */}
            <div className="space-y-3">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={endpoint}
                  onChange={(e) => setEndpoint(e.target.value)}
                  placeholder={t("setup.placeholder")}
                  className="eacn-input flex-1 !rounded-xl"
                  onKeyDown={(e) => { if (e.key === "Enter") handleConnect(); }}
                  autoFocus
                />
                <button
                  onClick={handleConnect}
                  disabled={loading || !endpoint.trim()}
                  className="px-5 py-2.5 rounded-xl text-sm font-semibold text-white transition-all disabled:opacity-40"
                  style={{
                    background: "linear-gradient(135deg, #0f766e, #174066)",
                    boxShadow: loading ? "none" : "0 18px 28px rgba(15,118,110,0.18)",
                  }}
                >
                  {loading ? t("setup.loading") : t("setup.connect")}
                </button>
              </div>

              {error && (
                <div className="text-xs text-red-500 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
                  {error}
                </div>
              )}
            </div>

            {/* Hint */}
            <div className="text-xs text-[#5f5a52]/70 leading-relaxed border-t border-[rgba(23,23,23,0.06)] pt-4">
              <p>{t("setup.hint")}</p>
              <div className="mt-3 p-3 rounded-xl font-mono text-[11px] text-[#94b6de]"
                style={{
                  background: "linear-gradient(180deg, rgba(23,64,102,0.96), rgba(21,34,56,0.98))",
                }}
              >
                <div className="text-[#5f5a52]/60 mb-1">
                  # {locale === "en" ? "Deploy the proxy" : "部署代理"}
                </div>
                <div>cd proxy && npx wrangler deploy</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
