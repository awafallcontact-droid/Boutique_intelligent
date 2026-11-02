// Stockage Cloudflare KV : état de la boutique, historique par client, doublons, quotas.
import { ETAT_INITIAL } from "./donnees.js";

export class Stockage {
  constructor(kv) {
    this.kv = kv;
  }

  async lireEtat() {
    return (await this.kv.get("etat", "json")) ?? structuredClone(ETAT_INITIAL);
  }

  async ecrireEtat(etat) {
    await this.kv.put("etat", JSON.stringify(etat));
  }

  // Dédoublonnage : Green API peut renvoyer une notification ; on garde chaque idMessage 3 jours.
  async dejaTraite(idMessage) {
    const cle = `msg:${idMessage}`;
    if (await this.kv.get(cle)) return true;
    await this.kv.put(cle, "1", { expirationTtl: 3 * 24 * 3600 });
    return false;
  }

  async historique(chatId) {
    return (await this.kv.get(`hist:${chatId}`, "json")) ?? [];
  }

  // Historique borné : seuls les N derniers messages repartent au LLM (coût d'entrée maîtrisé).
  async ecrireHistorique(chatId, historique, max) {
    await this.kv.put(`hist:${chatId}`, JSON.stringify(historique.slice(-max)));
  }

  async ajouterAuHistorique(chatId, message, max) {
    const h = await this.historique(chatId);
    h.push(message);
    await this.ecrireHistorique(chatId, h, max);
  }

  // Quota : nombre de messages de ce client dans l'heure en cours.
  async compterMessage(chatId, maintenant = new Date()) {
    const cle = `quota:${chatId}:${maintenant.toISOString().slice(0, 13)}`;
    const n = Number((await this.kv.get(cle)) ?? 0) + 1;
    await this.kv.put(cle, String(n), { expirationTtl: 2 * 3600 });
    return n;
  }
}
