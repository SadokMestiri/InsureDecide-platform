/**
 * InsureDecide — MLOpsContent
 * 4 onglets : Modèles ML | Prévisions Prophet | Anomalies (Isolation Forest) | Data Drift (Evidently)
 * FIXES : data.historique undefined, probability NaN, sidebar manquante
 */
import { useState, useEffect } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts';

const API = 'http://localhost:8000';

const fmt = (v, suffix = '') =>
  v == null || isNaN(v) ? '—' : `${Number(v).toLocaleString('fr-TN', { maximumFractionDigits: 1 })}${suffix}`;
const fmtTND = v =>
  v == null || isNaN(v) ? '—' : `${Number(v).toLocaleString('fr-TN', { maximumFractionDigits: 0 })} TND`;

function Badge({ label, color }) {
  const colors = {
    green: 'bg-green-100 text-green-800',
    red:   'bg-red-100 text-red-800',
    yellow:'bg-yellow-100 text-yellow-800',
    blue:  'bg-blue-100 text-blue-800',
    gray:  'bg-gray-100 text-gray-600',
  };
  return <span className={`px-2 py-0.5 rounded text-xs font-semibold ${colors[color] || colors.gray}`}>{label}</span>;
}

function SectionTitle({ children }) {
  return <h3 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 border-b border-blue-100 pb-1">{children}</h3>;
}

// ── ONGLET 1 : Modèles ML ──────────────────────────────────
function ModelsTab() {
  const [status,        setStatus]        = useState(null);
  const [training,      setTraining]      = useState(false);
  const [trainResult,   setTrainResult]   = useState(null);
  const [trainError,    setTrainError]    = useState(null);
  const [explainResult, setExplainResult] = useState(null);
  const [explaining,    setExplaining]    = useState(false);
  const [importance,    setImportance]    = useState(null);
  const [presets,       setPresets]       = useState([]);
  const [form, setForm] = useState({
    model: 'resiliation', ratio_combine_pct: 105, primes_acquises_tnd: 1500000,
    cout_sinistres_tnd: 900000, nb_sinistres: 150, provision_totale_tnd: 300000,
    nb_suspicions_fraude: 3, dept_code: 0, mois: 12, annee: 2024,
  });

  useEffect(() => {
    fetch(`${API}/api/ml/status`).then(r => r.json()).then(setStatus).catch(() => {});
    fetch(`${API}/api/ml/presets`).then(r => r.json()).then(d => setPresets(d.presets || [])).catch(() => {});
  }, []);

  const train = async () => {
    setTraining(true); setTrainError(null); setTrainResult(null);
    try {
      const r = await fetch(`${API}/api/ml/train`, { method: 'POST' });
      const d = await r.json();
      if (d.error || d.detail) setTrainError(d.error || d.detail);
      else {
        setTrainResult(d);
        fetch(`${API}/api/ml/status`).then(r => r.json()).then(setStatus).catch(() => {});
      }
    } catch (e) { setTrainError(String(e)); }
    setTraining(false);
  };

  const explain = async () => {
    setExplaining(true); setExplainResult(null); setImportance(null);
    try {
      const r = await fetch(`${API}/api/ml/explain`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form),
      });
      const d = await r.json();
      setExplainResult(d);
      const imp = await fetch(`${API}/api/ml/importance/${form.model}`);
      setImportance(await imp.json());
    } catch (e) { setExplainResult({ error: String(e) }); }
    setExplaining(false);
  };

  // Normaliser probability : API retourne déjà 0-100
  const probPct = explainResult?.probability != null
    ? (explainResult.probability > 1 ? explainResult.probability : explainResult.probability * 100)
    : null;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        {['resiliation', 'fraude'].map(m => {
          const info = status?.models?.[m];
          return (
            <div key={m} className="bg-white rounded-xl border p-4">
              <div className="flex justify-between items-center mb-2">
                <span className="font-semibold text-gray-700">{m === 'resiliation' ? 'Résiliation Critique' : 'Détection Fraude'}</span>
                <Badge label={info?.available ? '✓ Prêt' : '✗ Non entraîné'} color={info?.available ? 'green' : 'red'} />
              </div>
              <p className="text-xs text-gray-400">{m === 'resiliation' ? 'RandomForestClassifier' : 'GradientBoostingClassifier'}</p>
              {info?.available && (
                <div className="mt-2 grid grid-cols-3 gap-1 text-xs text-gray-500">
                  {info.accuracy && <span>Acc: {fmt(info.accuracy * 100, '%')}</span>}
                  {info.f1 && <span>F1: {fmt(info.f1 * 100, '%')}</span>}
                  {info.auc && <span>AUC: {fmt(info.auc * 100, '%')}</span>}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <button onClick={train} disabled={training}
        className="w-full py-3 bg-blue-700 text-white rounded-xl font-semibold hover:bg-blue-800 disabled:opacity-50 transition">
        {training ? '⏳ Entraînement en cours…' : '🚀 Lancer l\'entraînement (Résiliation + Fraude)'}
      </button>

      {trainError && <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">❌ {trainError}</div>}
      {trainResult && !trainError && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-sm space-y-1">
          <p className="font-bold text-green-800">✅ Entraînement terminé</p>
          {['resiliation', 'fraude'].map(m => trainResult[m] && (
            <div key={m} className="text-green-700">
              <p className="font-medium">{m === 'resiliation' ? '🎯 Résiliation' : '🔍 Fraude'}</p>
              <p className="text-xs ml-2">
                Accuracy: {fmt(trainResult[m].accuracy * 100, '%')} ·
                F1: {fmt(trainResult[m].f1 * 100, '%')} ·
                AUC test: {fmt(trainResult[m].auc * 100, '%')}
              </p>
              <p className="text-xs ml-2">
                CV AUC (5-fold): <strong>{fmt(trainResult[m].cv_auc * 100, '%')}</strong> ·
                Gap overfitting: <span className={trainResult[m].overfit_gap > 0.15 ? 'text-red-600 font-bold' : 'text-green-600'}>
                  {fmt(trainResult[m].overfit_gap * 100, '%')}
                  {trainResult[m].overfit_gap > 0.15 ? ' ⚠️' : ' ✓'}
                </span>
              </p>
            </div>
          ))}
        </div>
      )}

      {presets.length > 0 && (
        <div>
          <SectionTitle>Presets — Scénarios types</SectionTitle>
          <div className="grid grid-cols-3 gap-3">
            {presets.map((p, i) => (
              <button key={i} onClick={() => setForm({ model: p.model || form.model, ratio_combine_pct: p.ratio_combine_pct ?? form.ratio_combine_pct, primes_acquises_tnd: p.primes_acquises_tnd ?? form.primes_acquises_tnd, cout_sinistres_tnd: p.cout_sinistres_tnd ?? form.cout_sinistres_tnd, nb_sinistres: p.nb_sinistres ?? form.nb_sinistres, provision_totale_tnd: p.provision_totale_tnd ?? form.provision_totale_tnd, nb_suspicions_fraude: p.nb_suspicions_fraude ?? form.nb_suspicions_fraude, dept_code: p.dept_code ?? form.dept_code, mois: p.mois ?? form.mois, annee: p.annee ?? form.annee })}
                className="text-left p-3 bg-blue-50 hover:bg-blue-100 rounded-xl border border-blue-200 text-xs transition">
                <p className="font-semibold text-blue-800">{p.label}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <SectionTitle>Formulaire de prédiction SHAP</SectionTitle>
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div><label className="text-xs text-gray-500">Modèle</label>
            <select value={form.model} onChange={e => setForm({ ...form, model: e.target.value })} className="w-full border rounded-lg p-2 text-sm mt-1">
              <option value="resiliation">Résiliation Critique</option>
              <option value="fraude">Fraude</option>
            </select>
          </div>
          {[['ratio_combine_pct','Ratio combiné (%)'],['primes_acquises_tnd','Primes (TND)'],['cout_sinistres_tnd','Coût sinistres (TND)'],['nb_sinistres','Nb sinistres'],['provision_totale_tnd','Provisions (TND)'],['nb_suspicions_fraude','Suspicions fraude']].map(([k, l]) => (
            <div key={k}><label className="text-xs text-gray-500">{l}</label>
              <input type="number" value={form[k]} onChange={e => setForm({ ...form, [k]: parseFloat(e.target.value) || 0 })} className="w-full border rounded-lg p-2 text-sm mt-1" />
            </div>
          ))}
        </div>
        <button onClick={explain} disabled={explaining}
          className="w-full py-2 bg-green-700 text-white rounded-xl font-semibold hover:bg-green-800 disabled:opacity-50 transition">
          {explaining ? '⏳ Calcul SHAP…' : '🔍 Prédire + Expliquer (SHAP)'}
        </button>
      </div>

      {explainResult && !explainResult.error && (
        <div className="space-y-4">
          <div className={`rounded-xl p-4 text-center ${explainResult.prediction === 1 ? 'bg-red-50 border border-red-200' : 'bg-green-50 border border-green-200'}`}>
            <p className="text-2xl font-bold">{explainResult.prediction === 1 ? '⚠️ RISQUE DÉTECTÉ' : '✅ NORMAL'}</p>
            <p className="text-sm mt-1 text-gray-600">Probabilité : {probPct != null && !isNaN(probPct) ? fmt(probPct, '%') : '—'}</p>
            {explainResult.risque && <p className="text-xs mt-1 text-gray-500">Niveau : {explainResult.risque}</p>}
            {explainResult.explication && <p className="text-xs mt-2 text-gray-600 italic">{explainResult.explication}</p>}
          </div>

          {Array.isArray(explainResult.contributions) && explainResult.contributions.length > 0 && (
            <div><SectionTitle>Contributions SHAP</SectionTitle>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={explainResult.contributions.slice(0, 10)} layout="vertical" margin={{ left: 160 }}>
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={160} />
                  <Tooltip formatter={v => typeof v === 'number' ? v.toFixed(4) : v} />
                  <ReferenceLine x={0} stroke="#666" />
                  <Bar dataKey="shap_value" fill="#2563EB" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {Array.isArray(importance?.importance) && importance.importance.length > 0 && (
            <div><SectionTitle>Importance globale des features</SectionTitle>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={importance.importance.slice(0, 10)} layout="vertical" margin={{ left: 160 }}>
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={160} />
                  <Tooltip formatter={v => typeof v === 'number' ? v.toFixed(4) : v} />
                  <Bar dataKey="importance" fill="#10B981" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}
      {explainResult?.error && <div className="bg-red-50 text-red-700 p-4 rounded-xl text-sm">❌ {explainResult.error}</div>}
    </div>
  );
}

// ── ONGLET 2 : Prophet ────────────────────────────────────
function ForecastTab() {
  const [dept,    setDept]    = useState('Automobile');
  const [ind,     setInd]     = useState('primes_acquises_tnd');
  const [nbMois,  setNbMois]  = useState(6);
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);

  const indLabels = {
    primes_acquises_tnd: 'Primes acquises (TND)',
    cout_sinistres_tnd:  'Coût sinistres (TND)',
    nb_sinistres:        'Nombre de sinistres',
    ratio_combine_pct:   'Ratio combiné (%)',
  };

  const load = async () => {
    setLoading(true); setData(null);
    try {
      const r = await fetch(`${API}/api/ml/forecast?departement=${dept}&indicateur=${ind}&nb_mois=${nbMois}`);
      setData(await r.json());
    } catch (e) { setData({ error: String(e) }); }
    setLoading(false);
  };

  // FIX PRINCIPAL : vérifier l'existence avant slice
  const historique = Array.isArray(data?.historique) ? data.historique : [];
  const previsions = Array.isArray(data?.previsions) ? data.previsions : [];
  const chartData  = (data && !data.error) ? [
    ...historique.slice(-18).map(h => ({ periode: h.periode, reel: h.valeur })),
    ...previsions.map(p => ({ periode: p.periode, prevision: p.valeur })),
  ] : [];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <div><label className="text-xs text-gray-500 block mb-1">Département</label>
          <select value={dept} onChange={e => setDept(e.target.value)} className="w-full border rounded-lg p-2 text-sm">
            {['Automobile', 'Vie', 'Immobilier'].map(d => <option key={d}>{d}</option>)}
          </select>
        </div>
        <div><label className="text-xs text-gray-500 block mb-1">Indicateur</label>
          <select value={ind} onChange={e => setInd(e.target.value)} className="w-full border rounded-lg p-2 text-sm">
            {Object.entries(indLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div><label className="text-xs text-gray-500 block mb-1">Horizon</label>
          <select value={nbMois} onChange={e => setNbMois(Number(e.target.value))} className="w-full border rounded-lg p-2 text-sm">
            {[3, 6, 9, 12].map(n => <option key={n} value={n}>{n} mois</option>)}
          </select>
        </div>
      </div>

      <button onClick={load} disabled={loading}
        className="w-full py-3 bg-blue-700 text-white rounded-xl font-semibold hover:bg-blue-800 disabled:opacity-50 transition">
        {loading ? '⏳ Calcul Prophet…' : '📈 Générer les prévisions'}
      </button>

      {data && !data.error && (
        <>
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-blue-50 rounded-xl p-4 text-center">
              <p className="text-xs text-gray-500 mb-1">Dernière valeur</p>
              <p className="text-xl font-bold text-blue-800">{ind.includes('tnd') ? fmtTND(data.derniere_valeur) : fmt(data.derniere_valeur)}</p>
            </div>
            <div className="bg-green-50 rounded-xl p-4 text-center">
              <p className="text-xs text-gray-500 mb-1">Prochaine prévision</p>
              <p className="text-xl font-bold text-green-800">{ind.includes('tnd') ? fmtTND(data.prochaine_valeur) : fmt(data.prochaine_valeur)}</p>
            </div>
            <div className={`rounded-xl p-4 text-center ${data.tendance === 'hausse' ? 'bg-red-50' : data.tendance === 'baisse' ? 'bg-green-50' : 'bg-gray-50'}`}>
              <p className="text-xs text-gray-500 mb-1">Tendance</p>
              <p className="text-xl font-bold">
                {data.tendance === 'hausse' ? '📈' : data.tendance === 'baisse' ? '📉' : '➡️'} {data.variation_pct > 0 ? '+' : ''}{data.variation_pct}%
              </p>
            </div>
          </div>

          {chartData.length > 0 && (
            <div className="bg-white rounded-xl border p-4">
              <SectionTitle>Historique + Prévisions</SectionTitle>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="periode" tick={{ fontSize: 10 }} interval={2} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip /><Legend />
                  <Line type="monotone" dataKey="reel"      stroke="#2563EB" strokeWidth={2} dot={false} name="Réel" />
                  <Line type="monotone" dataKey="prevision" stroke="#10B981" strokeWidth={2} strokeDasharray="5 5" dot={false} name="Prévision" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {previsions.length > 0 && (
            <table className="w-full text-sm border border-gray-200 rounded-xl overflow-hidden">
              <thead className="bg-blue-700 text-white">
                <tr>{['Période', 'Prévision', 'Min (95%)', 'Max (95%)'].map(h => <th key={h} className="px-4 py-2 text-left text-xs">{h}</th>)}</tr>
              </thead>
              <tbody>
                {previsions.map((p, i) => (
                  <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                    <td className="px-4 py-2 font-medium">{p.periode}</td>
                    <td className="px-4 py-2 font-bold text-blue-700">{ind.includes('tnd') ? fmtTND(p.valeur) : fmt(p.valeur)}</td>
                    <td className="px-4 py-2 text-gray-500">{ind.includes('tnd') ? fmtTND(p.valeur_min) : fmt(p.valeur_min)}</td>
                    <td className="px-4 py-2 text-gray-500">{ind.includes('tnd') ? fmtTND(p.valeur_max) : fmt(p.valeur_max)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {data?.error && <div className="bg-red-50 text-red-700 p-4 rounded-xl text-sm">❌ {data.error}</div>}
    </div>
  );
}

// ── ONGLET 3 : Isolation Forest ───────────────────────────
function AnomaliesTab() {
  const [dept,          setDept]          = useState('');
  const [contamination, setContamination] = useState(0.1);
  const [data,          setData]          = useState(null);
  const [loading,       setLoading]       = useState(false);

  const load = async () => {
    setLoading(true); setData(null);
    try {
      const p = new URLSearchParams({ contamination });
      if (dept) p.append('departement', dept);
      const r = await fetch(`${API}/api/ml/anomalies?${p}`);
      setData(await r.json());
    } catch (e) { setData({ error: String(e) }); }
    setLoading(false);
  };

  const anomalies = Array.isArray(data?.anomalies) ? data.anomalies : [];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <div><label className="text-xs text-gray-500 block mb-1">Département</label>
          <select value={dept} onChange={e => setDept(e.target.value)} className="w-full border rounded-lg p-2 text-sm">
            <option value="">Tous</option>
            {['Automobile', 'Vie', 'Immobilier'].map(d => <option key={d}>{d}</option>)}
          </select>
        </div>
        <div><label className="text-xs text-gray-500 block mb-1">Contamination attendue</label>
          <select value={contamination} onChange={e => setContamination(Number(e.target.value))} className="w-full border rounded-lg p-2 text-sm">
            {[0.05, 0.1, 0.15, 0.2].map(v => <option key={v} value={v}>{(v * 100).toFixed(0)}%</option>)}
          </select>
        </div>
      </div>

      <button onClick={load} disabled={loading}
        className="w-full py-3 bg-orange-600 text-white rounded-xl font-semibold hover:bg-orange-700 disabled:opacity-50 transition">
        {loading ? '⏳ Détection…' : '🔍 Détecter les anomalies (Isolation Forest)'}
      </button>

      {data && !data.error && (
        <>
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-red-50 rounded-xl p-4 text-center">
              <p className="text-xs text-gray-500 mb-1">Anomalies</p>
              <p className="text-3xl font-bold text-red-700">{data.nb_anomalies ?? 0}</p>
            </div>
            <div className="bg-green-50 rounded-xl p-4 text-center">
              <p className="text-xs text-gray-500 mb-1">Normaux</p>
              <p className="text-3xl font-bold text-green-700">{data.nb_normaux ?? 0}</p>
            </div>
            <div className="bg-orange-50 rounded-xl p-4 text-center">
              <p className="text-xs text-gray-500 mb-1">Dept. le plus impacté</p>
              <p className="text-lg font-bold text-orange-700">{data.stats?.top_departement || '—'}</p>
            </div>
          </div>

          {anomalies.length > 0 && (
            <div>
              <SectionTitle>Périodes anomales détectées</SectionTitle>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border rounded-xl overflow-hidden">
                  <thead className="bg-orange-600 text-white">
                    <tr>{['Période','Département','Score risque','Ratio combiné','Résiliation','Features déviantes'].map(h => <th key={h} className="px-3 py-2 text-left text-xs whitespace-nowrap">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {anomalies.map((a, i) => (
                      <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-orange-50'}>
                        <td className="px-3 py-2 font-medium whitespace-nowrap">{a.periode}</td>
                        <td className="px-3 py-2">{a.departement}</td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            <div className="w-16 bg-gray-200 rounded-full h-2">
                              <div className="h-2 rounded-full bg-red-500" style={{ width: `${Math.min(a.risk_score, 100)}%` }} />
                            </div>
                            <span className="font-bold text-red-700 text-xs">{a.risk_score}</span>
                          </div>
                        </td>
                        <td className="px-3 py-2">{fmt(a.ratio_combine_pct, '%')}</td>
                        <td className="px-3 py-2">{fmt(a.taux_resiliation_pct, '%')}</td>
                        <td className="px-3 py-2 text-xs text-gray-500">
                          {Array.isArray(a.features_deviantes) ? a.features_deviantes.map(f => f.feature?.replace(/_/g, ' ')).join(', ') : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
      {data?.error && <div className="bg-red-50 text-red-700 p-4 rounded-xl text-sm">❌ {data.error}</div>}
    </div>
  );
}

// ── ONGLET 4 : Data Drift ─────────────────────────────────
function DriftTab() {
  const [dept,    setDept]    = useState('');
  const [refMois, setRefMois] = useState(12);
  const [curMois, setCurMois] = useState(6);
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true); setData(null);
    try {
      const p = new URLSearchParams({ nb_mois_reference: refMois, nb_mois_courant: curMois });
      if (dept) p.append('departement', dept);
      const r = await fetch(`${API}/api/ml/drift?${p}`);
      setData(await r.json());
    } catch (e) { setData({ error: String(e) }); }
    setLoading(false);
  };

  const features    = Array.isArray(data?.features)    ? data.features    : [];
  const comparaison = Array.isArray(data?.comparaison) ? data.comparaison : [];

  return (
    <div className="space-y-6">
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
        <strong>Evidently AI + Kolmogorov-Smirnov</strong> — Compare la distribution des KPIs sur deux fenêtres temporelles pour détecter si le comportement des données a changé.
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div><label className="text-xs text-gray-500 block mb-1">Département</label>
          <select value={dept} onChange={e => setDept(e.target.value)} className="w-full border rounded-lg p-2 text-sm">
            <option value="">Tous</option>
            {['Automobile', 'Vie', 'Immobilier'].map(d => <option key={d}>{d}</option>)}
          </select>
        </div>
        <div><label className="text-xs text-gray-500 block mb-1">Référence (mois)</label>
          <select value={refMois} onChange={e => setRefMois(Number(e.target.value))} className="w-full border rounded-lg p-2 text-sm">
            {[6, 12, 18, 24].map(n => <option key={n} value={n}>{n} mois</option>)}
          </select>
        </div>
        <div><label className="text-xs text-gray-500 block mb-1">Courant (mois)</label>
          <select value={curMois} onChange={e => setCurMois(Number(e.target.value))} className="w-full border rounded-lg p-2 text-sm">
            {[3, 6, 9, 12].map(n => <option key={n} value={n}>{n} mois</option>)}
          </select>
        </div>
      </div>

      <button onClick={load} disabled={loading}
        className="w-full py-3 bg-purple-700 text-white rounded-xl font-semibold hover:bg-purple-800 disabled:opacity-50 transition">
        {loading ? '⏳ Analyse Evidently…' : '📊 Analyser le Data Drift'}
      </button>

      {data && !data.error && (
        <>
          <div className={`rounded-xl p-5 border-2 ${
            data.niveau === 'critique' ? 'bg-red-50 border-red-300' :
            data.niveau === 'warning'  ? 'bg-yellow-50 border-yellow-300' : 'bg-green-50 border-green-300'
          }`}>
            <div className="flex justify-between items-center">
              <div>
                <p className="text-xl font-bold">
                  {data.niveau === 'critique' ? '🔴 Drift critique' : data.niveau === 'warning' ? '🟡 Drift modéré' : '🟢 Pas de drift'}
                </p>
                <p className="text-sm text-gray-600 mt-1">{data.message}</p>
              </div>
              <div className="text-right">
                <p className="text-3xl font-bold text-purple-700">{data.nb_features_drift}/{data.nb_features_total}</p>
                <p className="text-xs text-gray-500">features en drift</p>
                <p className="text-xs text-gray-400 mt-1">{((data.share_drift || 0) * 100).toFixed(0)}% du dataset</p>
              </div>
            </div>
          </div>

          {comparaison.length > 0 && (
            <div>
              <SectionTitle>Référence vs Courant — Comparaison moyennes</SectionTitle>
              <table className="w-full text-sm border rounded-xl overflow-hidden">
                <thead className="bg-purple-700 text-white">
                  <tr>{['Feature','Moy. référence','Moy. courant','Variation'].map(h => <th key={h} className="px-4 py-2 text-left text-xs">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {comparaison.map((c, i) => (
                    <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-purple-50'}>
                      <td className="px-4 py-2 font-medium">{c.feature?.replace(/_/g, ' ')}</td>
                      <td className="px-4 py-2">{fmt(c.moyenne_ref)}</td>
                      <td className="px-4 py-2">{fmt(c.moyenne_cur)}</td>
                      <td className="px-4 py-2">
                        <span className={`font-bold ${Math.abs(c.variation_pct) > 20 ? (c.variation_pct > 0 ? 'text-red-600' : 'text-orange-600') : Math.abs(c.variation_pct) > 5 ? 'text-orange-500' : 'text-green-600'}`}>
                          {c.variation_pct > 0 ? '+' : ''}{c.variation_pct}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {features.length > 0 && (
            <div>
              <SectionTitle>Drift par feature (test Kolmogorov-Smirnov)</SectionTitle>
              <div className="grid grid-cols-2 gap-3">
                {features.map((f, i) => (
                  <div key={i} className={`rounded-xl p-3 border ${f.drift_detecte ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'}`}>
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-medium">{f.feature?.replace(/_/g, ' ')}</span>
                      <Badge label={f.drift_detecte ? 'Drift' : 'OK'} color={f.drift_detecte ? 'red' : 'green'} />
                    </div>
                    <div className="text-xs text-gray-500 mt-1 space-y-0.5">
                      <p>p-value : <strong>{f.p_value ?? '—'}</strong></p>
                      <p>statistic : {f.statistic ?? '—'}</p>
                      <p className="italic">{f.methode}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
      {data?.error && <div className="bg-red-50 text-red-700 p-4 rounded-xl text-sm">❌ {data.error}</div>}
    </div>
  );
}

// ── COMPOSANT PRINCIPAL ───────────────────────────────────
const TABS = [
  { id: 'models',    label: '🤖 Modèles ML' },
  { id: 'forecast',  label: '📈 Prévisions Prophet' },
  { id: 'anomalies', label: '🔍 Anomalies' },
  { id: 'drift',     label: '📊 Data Drift' },
];

export default function MLOpsContent() {
  const [tab, setTab] = useState('models');
  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">MLOps & Intelligence Artificielle</h2>
        <p className="text-gray-500 text-sm mt-1">Modèles prédictifs · Prévisions Prophet · Anomalies Isolation Forest · Data Drift Evidently AI</p>
      </div>
      <div className="flex gap-2 border-b border-gray-200 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition whitespace-nowrap ${tab === t.id ? 'bg-blue-700 text-white' : 'text-gray-600 hover:bg-gray-100'}`}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="bg-gray-50 rounded-xl p-6">
        {tab === 'models'    && <ModelsTab />}
        {tab === 'forecast'  && <ForecastTab />}
        {tab === 'anomalies' && <AnomaliesTab />}
        {tab === 'drift'     && <DriftTab />}
      </div>
    </div>
  );
}