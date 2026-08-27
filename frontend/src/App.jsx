import React, { useState, useEffect } from 'react';

export default function App() {
  const [models, setModels] = useState(["llama3.2:1b", "qwen2.5:0.5b"]);
  const [selectedModel, setSelectedModel] = useState("llama3.2:1b");
  const [prompt, setPrompt] = useState("Does tenure predict customer churn?");
  const [seed, setSeed] = useState(17);
  
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isReverifying, setIsReverifying] = useState(false);
  
  const [currentClaim, setCurrentClaim] = useState(null);
  const [reverificationResult, setReverificationResult] = useState(null);
  const [showCode, setShowCode] = useState(false);
  const [driftMode, setDriftMode] = useState("library_drift");

  useEffect(() => {
    fetch("/api/models")
      .then(res => res.json())
      .then(data => {
        if (data.models && data.models.length > 0) {
          setModels(data.models);
          setSelectedModel(data.models[0]);
        }
      })
      .catch(() => {});
  }, []);

  const handleRunAnalysis = async () => {
    setIsAnalyzing(true);
    setReverificationResult(null);
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          model_name: selectedModel,
          seed: parseInt(seed) || 17
        })
      });
      const data = await res.json();
      setCurrentClaim(data);
    } catch (err) {
      alert("Error executing analysis: " + err.message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleReverify = async () => {
    if (!currentClaim) return;
    setIsReverifying(true);
    try {
      const res = await fetch("/api/reverify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          claim_id: currentClaim.claim_id,
          simulate_drift: driftMode !== "clean",
          drift_type: driftMode
        })
      });
      const data = await res.json();
      setReverificationResult(data);
    } catch (err) {
      alert("Error during re-verification: " + err.message);
    } finally {
      setIsReverifying(false);
    }
  };

  const getClaimText = () => {
    if (!currentClaim) return "";
    const res = currentClaim.original_result;
    if (res.claim) return res.claim;
    if (res.r !== undefined) return `Tenure is negatively correlated with churn (r = ${res.r})`;
    if (res.value !== undefined) return `Computed value: ${res.value}`;
    return JSON.stringify(res);
  };

  const truncateHash = (hash) => {
    if (!hash || hash.length < 10) return hash || "—";
    return `${hash.slice(0, 4)}...${hash.slice(-2)}`;
  };

  return (
    <div className="min-h-screen bg-[#0c0c0e] text-zinc-100 p-4 md:p-8 flex justify-center items-start font-sans">
      <div className="w-full max-w-2xl space-y-6">
        
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-[#232328]">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400 font-bold text-sm">
              PL
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Provenance Ledger</h1>
          </div>
          <div className="flex items-center space-x-2">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-800/50">
              ● Postgres 16
            </span>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-950/80 text-blue-400 border border-blue-800/50">
              ● Ollama
            </span>
          </div>
        </div>

        {/* CARD 1: 1. Ask the agent */}
        <div className="bg-[#161618] border border-[#28282c] rounded-2xl p-6 shadow-xl">
          <div className="text-sm font-medium text-zinc-400 mb-3">1. Ask the agent</div>

          <div className="space-y-3">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Enter question for data analysis..."
              className="w-full px-4 py-3 bg-[#111113] border border-[#2e2e34] rounded-xl text-zinc-100 text-base focus:outline-none focus:border-blue-500 transition-colors"
            />

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <div className="flex items-center space-x-2">
                <span className="text-xs text-zinc-400">Model:</span>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="px-2.5 py-1.5 bg-[#111113] border border-[#2e2e34] rounded-lg text-xs text-zinc-200 focus:outline-none"
                >
                  {models.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>

                <span className="text-xs text-zinc-400 ml-2">Seed:</span>
                <input
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  className="w-14 px-2 py-1 bg-[#111113] border border-[#2e2e34] rounded-lg text-xs text-zinc-200 text-center focus:outline-none"
                />
              </div>

              <button
                onClick={handleRunAnalysis}
                disabled={isAnalyzing}
                className="px-4 py-2 bg-[#1e1e24] hover:bg-[#282830] border border-[#383842] rounded-lg text-sm font-medium text-zinc-200 flex items-center space-x-2 shadow-sm disabled:opacity-50"
              >
                <span>{isAnalyzing ? "Analyzing..." : "▶ Run analysis"}</span>
              </button>
            </div>
          </div>

          {currentClaim && (
            <div className="mt-6 pt-5 border-t border-[#232328]">
              <div className="text-xs font-medium text-zinc-400 mb-1">Agent's claim</div>
              <div className="text-lg font-bold text-zinc-100 tracking-tight">
                {getClaimText()}
              </div>

              <div className="mt-3">
                <button
                  onClick={() => setShowCode(!showCode)}
                  className="text-xs text-zinc-400 hover:text-zinc-200 flex items-center space-x-1"
                >
                  <span>{showCode ? "▼ Hide generated code" : "▶ View generated code"}</span>
                </button>
                {showCode && (
                  <pre className="mt-2 p-3 bg-[#0d0d0f] border border-[#222226] rounded-lg text-xs font-mono text-emerald-400 overflow-x-auto">
                    {currentClaim.generated_code}
                  </pre>
                )}
              </div>
            </div>
          )}
        </div>

        {/* CARD 2: 2. Ledger entry for this claim */}
        {currentClaim && (
          <div className="bg-[#161618] border border-[#28282c] rounded-2xl p-6 shadow-xl space-y-5">
            <div className="text-sm font-medium text-zinc-400">2. Ledger entry for this claim</div>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between items-center py-1">
                <span className="text-zinc-400">Model</span>
                <span className="font-mono text-zinc-200">{currentClaim.model_name}, seed {currentClaim.seed}</span>
              </div>
              <div className="flex justify-between items-center py-1">
                <span className="text-zinc-400">Data hash</span>
                <span className="font-mono text-zinc-200">{truncateHash(currentClaim.data_snapshot_hash)}</span>
              </div>
              <div className="flex justify-between items-center py-1">
                <span className="text-zinc-400">Env hash</span>
                <span className="font-mono text-zinc-200">{truncateHash(currentClaim.env_hash)}</span>
              </div>
            </div>

            <div className="pt-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-t border-[#232328]">
              <div className="flex items-center space-x-2 text-xs">
                <span className="text-zinc-400">Audit Mode:</span>
                <select
                  value={driftMode}
                  onChange={(e) => setDriftMode(e.target.value)}
                  className="px-2 py-1 bg-[#111113] border border-[#2e2e34] rounded-lg text-xs text-zinc-300 focus:outline-none"
                >
                  <option value="library_drift">Simulate Library Drift (pandas 2.1.0 → 2.2.0)</option>
                  <option value="clean">Clean Verification (Exact Match)</option>
                  <option value="data_drift">Simulate Data Shift</option>
                </select>
              </div>

              <button
                onClick={handleReverify}
                disabled={isReverifying}
                className="px-4 py-2 bg-[#1e1e24] hover:bg-[#282830] border border-[#383842] rounded-lg text-sm font-medium text-zinc-200 flex items-center space-x-2 disabled:opacity-50"
              >
                <span>{isReverifying ? "Verifying..." : "🔄 Re-verify now"}</span>
              </button>
            </div>

            {reverificationResult && (
              <div className="pt-2">
                {!reverificationResult.matched ? (
                  <div className="p-4 rounded-xl bg-[#281013] border border-[#521c22] text-[#fca5a5] space-y-1">
                    <div className="flex items-center space-x-2 font-semibold text-sm text-[#f87171]">
                      <span>☒ Did not reproduce</span>
                    </div>
                    <div className="text-xs text-[#fca5a5] leading-relaxed">
                      {reverificationResult.diff_summary}
                    </div>
                  </div>
                ) : (
                  <div className="p-4 rounded-xl bg-[#0e271a] border border-[#164e2e] text-[#86efac] space-y-1">
                    <div className="flex items-center space-x-2 font-semibold text-sm text-[#4ade80]">
                      <span>☑ Reproduced successfully</span>
                    </div>
                    <div className="text-xs text-[#bbf7d0] leading-relaxed">
                      {reverificationResult.diff_summary}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
