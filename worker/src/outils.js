// Les 5 outils, portés du palier 1. En production, creer_commande N'ENREGISTRE PAS :
// il met la commande en attente et envoie le récapitulatif à Afi sur son WhatsApp.
import { devis, fcfa, normaliser, produit, trouverZone } from "./donnees.js";

const MOTS_VIDES = new Set(["de", "des", "du", "en", "le", "la", "les", "un", "une", "pour", "et", "a"]);
const mots = (t) => normaliser(t).split(" ").filter((m) => !MOTS_VIDES.has(m) && m.length >= 3)
  .map((m) => (m.endsWith("s") && m.length > 3 ? m.slice(0, -1) : m));

const objet = (proprietes, requis) => ({ type: "object", properties: proprietes, required: requis });

export const SCHEMAS = [
  ["chercher_produits", "Trouve des produits du catalogue par mot-clé (ex. 'pagne', 'robe', 'karité') et donne leur référence et leur prix en FCFA. À utiliser dès que le client parle d'un produit. Mot-clé 'catalogue' pour tout lister.",
    objet({ mot_cle: { type: "string" } }, ["mot_cle"])],
  ["verifier_stock", "Donne le stock d'une référence (ex. 'P05'). À utiliser AVANT de dire qu'un produit est disponible ou d'accepter une quantité. En cas de rupture, renvoie les alternatives en stock.",
    objet({ ref: { type: "string" } }, ["ref"])],
  ["frais_livraison", "Donne les frais (FCFA) et le délai de livraison pour une zone. À utiliser dès que le client indique où livrer, et avant d'annoncer un total.",
    objet({ zone: { type: "string" } }, ["zone"])],
  ["convertir_devise", "Convertit un montant en FCFA vers une devise (code ISO : EUR, USD, NGN...) au taux réel du moment. À utiliser dès que le client veut un prix dans sa devise.",
    objet({ montant_fcfa: { type: "number" }, devise: { type: "string" } }, ["montant_fcfa", "devise"])],
  ["creer_commande", "Transmet une commande à Afi pour validation. ACTION IRRÉVERSIBLE : seulement après un oui explicite du client au récapitulatif (articles, livraison, total).",
    objet({
      client: { type: "string", description: "Nom du client" },
      zone: { type: "string" },
      articles: { type: "array", items: objet({ ref: { type: "string" }, quantite: { type: "integer" } }, ["ref", "quantite"]) },
    }, ["client", "zone", "articles"])],
].map(([name, description, parameters]) => ({ type: "function", function: { name, description, parameters } }));

export function recapPourAfi(c) {
  const articles = c.lignes.map((l) => `${l.quantite} x ${l.nom}`).join(", ");
  return `Commande #${c.numero} : ${articles}, ${c.zone}, ${fcfa(c.total)}. ` +
    `Client : ${c.client} (${c.chatId.replace("@c.us", "")}). ` +
    `Répondez OUI ${c.numero} ou NON ${c.numero}`;
}

export function creerOutils({ env, etat, stockage, chatId, clientAConfirme, envoyer, fetchFn }) {
  return {
    async chercher_produits({ mot_cle = "" }) {
      const q = mots(mot_cle);
      const trouves = ["tout", "catalogue", "produits"].includes(normaliser(mot_cle)) ? etat.produits
        : etat.produits.filter((p) => q.some((x) => mots(p.nom).some((m) => m === x || (x.length >= 4 && m.startsWith(x)))));
      if (!trouves.length) return { erreur: `aucun produit pour ${mot_cle}` };
      return { produits: trouves.map((p) => ({ ref: p.ref, nom: p.nom, prix_fcfa: p.prix })) };
    },

    async verifier_stock({ ref = "" }) {
      const p = produit(etat, ref);
      if (!p) return { erreur: "référence inconnue", ref };
      const r = { ref: p.ref, nom: p.nom, prix_fcfa: p.prix, stock: p.stock, statut: p.stock > 0 ? "disponible" : "rupture" };
      if (p.stock === 0) {
        r.alternatives_en_stock = etat.produits.filter((a) => a.stock > 0)
          .map((a) => ({ ref: a.ref, nom: a.nom, prix_fcfa: a.prix, stock: a.stock }));
      }
      return r;
    },

    async frais_livraison({ zone = "" }) {
      const z = trouverZone(etat, zone);
      if (!z) return { erreur: "zone non desservie", zones_desservies: Object.keys(etat.zones) };
      return { zone: z.zone, frais_fcfa: z.frais, delai: etat.delai };
    },

    async convertir_devise({ montant_fcfa, devise = "" }) {
      let donnees;
      try {
        const r = await fetchFn(env.API_CHANGE_URL ?? "https://open.er-api.com/v6/latest/XOF");
        donnees = await r.json();
      } catch {
        return { erreur: "service de change indisponible, réessayer plus tard" };
      }
      const code = String(devise).trim().toUpperCase();
      const taux = donnees?.rates?.[code];
      if (taux === undefined || code === "XOF") return { erreur: "devise non prise en charge", devise };
      return { montant_fcfa, devise: code, montant_converti: Math.round(montant_fcfa * taux * 100) / 100,
               taux_1_fcfa: taux, date_du_taux: donnees.time_last_update_utc, source: "open.er-api.com" };
    },

    async creer_commande({ client, zone, articles }) {
      if (!clientAConfirme) {
        return { refus: "Le client n'a pas encore donné son accord explicite. Présente le récapitulatif et demande-lui de confirmer." };
      }
      const d = devis(etat, zone, articles);
      if (d.erreur) return d;
      const commande = { numero: etat.prochain_numero++, chatId, client, ...d, date: new Date().toISOString() };
      etat.en_attente[commande.numero] = commande;
      await stockage.ecrireEtat(etat);
      await envoyer(env.AFI_CHAT_ID, recapPourAfi(commande));
      return { statut: "en attente de validation d'Afi", numero: commande.numero, total_fcfa: d.total,
               consigne: "Dis au client que sa commande est transmise à Afi et qu'il sera prévenu de sa décision. Ne dis pas qu'elle est validée." };
    },
  };
}
