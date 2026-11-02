// Évaluation avant envoi : règle en code sur le total, puis LLM juge (port de evaluation.py).
import { devis } from "./donnees.js";

const CRITERES = `1. Aucun chiffre inventé : chaque prix, stock, frais, délai, taux ou montant converti figure dans les observations des outils, ou se calcule directement à partir d'elles (quantité x prix, somme, total). Quantités demandées et numéros de commande permis. Sans observation, aucun prix.
2. Si une observation indique une rupture, la réponse le dit et propose une alternative tirée des observations.
3. La réponse fait moins de 80 mots.`;

const RE_TOTAL = /total[^0-9\n]*?(\d[\d .]*\d|\d)\s*f\s?cfa/gi;
const RE_LIGNE = /(\d+)\s*[x×]\s*[^\n(]*\((P\d{2})\)/gi;
const RE_LIVRAISON = /livraison\s+(?:à\s+|a\s+)?([^\n:(]+?)\s*:/i;

const nettoyer = (t) => t.replace(/[  ]/g, " ").replace(/[*_~]/g, "");

export function verifierTotal(texte, etat) {
  const t = nettoyer(texte);
  const totaux = [...t.matchAll(RE_TOTAL)].filter((m) => !/sous/i.test(t.slice(Math.max(0, m.index - 5), m.index)));
  if (!totaux.length) return { ok: true, source: "règle" };
  const annonce = Number(totaux.at(-1)[1].replace(/\D/g, ""));
  const lignes = [...t.matchAll(RE_LIGNE)].map((m) => ({ ref: m[2].toUpperCase(), quantite: Number(m[1]) }));
  const zone = t.match(RE_LIVRAISON);
  if (!lignes.length || !zone) {
    return { ok: false, source: "règle", critique: "Tu annonces un total sans récapitulatif vérifiable. Écris « - <quantité> x <nom> (<réf>) : <montant> FCFA », puis « Livraison <zone> : <frais> FCFA », puis « Total : <total> FCFA »." };
  }
  const d = devis(etat, zone[1].trim(), lignes);
  if (d.erreur) return { ok: false, source: "règle", critique: `Récapitulatif impossible à honorer : ${d.erreur}. Retire l'article concerné ou corrige la zone.` };
  if (annonce !== d.total) return { ok: false, source: "règle", critique: `Total faux : tu annonces ${annonce} FCFA, mais articles + livraison = ${d.total} FCFA.` };
  return { ok: true, source: "règle" };
}

export async function jugerAvecLLM(llm, modele, texte, observations, demande) {
  const brut = (await llm.chat([
    { role: "system", content: `Tu es l'évaluateur qualité d'un vendeur WhatsApp. Critères :\n${CRITERES}\nRéponds uniquement en JSON : {"verdict": "ok" | "pas encore", "critique": "..."}.` },
    { role: "user", content: `Demande du client :\n${demande}\n\nObservations des outils (JSON) :\n${JSON.stringify(observations)}\n\nRéponse proposée :\n${texte}\n\nNombre de mots (compté par le code) : ${texte.split(/\s+/).filter(Boolean).length}` },
  ], null, modele)).content ?? "";
  let avis = {};
  try { avis = JSON.parse(brut.match(/\{[\s\S]*\}/)?.[0] ?? "{}"); } catch { /* illisible */ }
  if (!["ok", "pas encore"].includes(avis.verdict)) {
    return { ok: false, source: "juge", critique: "Évaluation illisible, reformule en respectant les règles." };
  }
  return { ok: avis.verdict === "ok", source: "juge", critique: avis.critique ?? "" };
}

export function creerEvaluateur(llm, env, etat) {
  return async (texte, observations, historique) => {
    const v = verifierTotal(texte, etat);
    if (!v.ok) return v;
    const demande = historique.findLast((m) => m.role === "user")?.content ?? "";
    return jugerAvecLLM(llm, env.MODELE_JUGE ?? env.MODELE, texte, observations, demande);
  };
}
