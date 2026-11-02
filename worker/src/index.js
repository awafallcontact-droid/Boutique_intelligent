// Palier 3 : le harness en production.
// Green API --webhook--> ce Worker --> agent (RodiumAi + outils + KV) --sendMessage--> client / Afi
import { lancerAgent, REPONSE_SECOURS } from "./agent.js";
import { devis, fcfa, normaliser } from "./donnees.js";
import { creerEvaluateur } from "./evaluation.js";
import { creerEnvoi, creerLLM } from "./externe.js";
import { creerOutils, SCHEMAS } from "./outils.js";
import { Stockage } from "./stockage.js";

const RE_DECISION = /^\s*(oui|non)\s*#?\s*(\d+)\s*$/i;
const RE_OUI = /\b(oui|je confirme|confirme|confirmer|d accord|ok|je valide|valide|c est bon)\b/;
const RE_NON = /\b(non|pas d accord|annule)\b/;

// Règle 4 côté code : l'accord du client se lit dans SON dernier message, pas dans l'avis du LLM.
export function estConfirmation(texte) {
  const t = normaliser(texte).replace(/['’]/g, " ");
  return RE_OUI.test(t) && !RE_NON.test(t);
}

function extraireTexte(md) {
  if (md?.typeMessage === "textMessage") return md.textMessageData?.textMessage ?? "";
  if (md?.typeMessage === "extendedTextMessage") return md.extendedTextMessageData?.text ?? "";
  return ""; // médias, localisation, etc. : ignorés
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") return new Response("Boutique intelligente : en ligne");
    if (request.method !== "POST" || url.pathname !== "/webhook") return new Response("Introuvable", { status: 404 });

    // Jeton de webhook : Green API l'envoie dans l'en-tête Authorization.
    if (request.headers.get("Authorization") !== `Bearer ${env.WEBHOOK_TOKEN}`) {
      return new Response("Non autorisé", { status: 401 });
    }
    let notification;
    try {
      notification = await request.json();
    } catch {
      return new Response("JSON invalide", { status: 400 });
    }
    // Répondre 200 tout de suite ; l'agent tourne en arrière-plan.
    ctx.waitUntil(traiterNotification(notification, env).catch((e) =>
      console.error(JSON.stringify({ type: "exception", message: String(e) }))));
    return new Response("ok");
  },
};

export async function traiterNotification(notif, env, fetchFn = (...a) => fetch(...a)) {
  if (notif?.typeWebhook !== "incomingMessageReceived") return "ignoré : type";
  const chatId = notif.senderData?.chatId ?? "";
  if (!chatId.endsWith("@c.us")) return "ignoré : groupe ou inconnu"; // groupes en @g.us
  const texte = extraireTexte(notif.messageData).trim();
  if (!texte) return "ignoré : pas de texte";

  const stockage = new Stockage(env.BOUTIQUE);
  const journal = (e) => console.log(JSON.stringify({ chatId, idMessage: notif.idMessage, ...e }));
  if (await stockage.dejaTraite(notif.idMessage)) {
    journal({ type: "doublon" });
    return "doublon";
  }
  const envoyer = creerEnvoi(env, fetchFn);
  const historiqueMax = Number(env.HISTORIQUE_MAX ?? 10);

  // Validation humaine : seul le numéro d'Afi peut valider ou refuser.
  const decision = texte.match(RE_DECISION);
  if (decision) {
    if (chatId !== env.AFI_CHAT_ID) {
      journal({ type: "decision_refusee", texte });
      await envoyer(chatId, "Désolé, seule la gérante de la boutique peut valider ou refuser une commande.");
      return "refus : pas Afi";
    }
    await traiterDecisionAfi(env, stockage, envoyer, decision[1].toUpperCase(), Number(decision[2]), historiqueMax, journal);
    return "décision Afi";
  }
  if (chatId === env.AFI_CHAT_ID) {
    await envoyer(chatId, "Pour décider d'une commande, répondez OUI <numéro> ou NON <numéro> (ex. OUI 12).");
    return "aide Afi";
  }

  // Budget : plafond de messages par client et par heure.
  const plafond = Number(env.MESSAGES_MAX_PAR_HEURE ?? 30);
  const n = await stockage.compterMessage(chatId);
  if (n > plafond) {
    journal({ type: "quota", n });
    if (n === plafond + 1) {
      await envoyer(chatId, "Vous nous avez écrit beaucoup de messages en peu de temps. Afi vous répondra personnellement un peu plus tard, merci de votre patience !");
    }
    return "quota";
  }

  const historique = await stockage.historique(chatId);
  historique.push({ role: "user", content: texte });
  const etat = await stockage.lireEtat();
  const llm = creerLLM(env, fetchFn);
  let reponse;
  try {
    reponse = await lancerAgent({
      llm, schemas: SCHEMAS, historique, journal,
      outils: creerOutils({ env, etat, stockage, chatId, clientAConfirme: estConfirmation(texte), envoyer, fetchFn }),
      evaluer: creerEvaluateur(llm, env, etat),
      maxSteps: Number(env.MAX_STEPS ?? 8),
      maxReprises: Number(env.MAX_REPRISES ?? 2),
    });
  } catch (e) {
    journal({ type: "exception_agent", message: String(e) });
    reponse = REPONSE_SECOURS;
  }
  await envoyer(chatId, reponse);
  historique.push({ role: "assistant", content: reponse });
  await stockage.ecrireHistorique(chatId, historique, historiqueMax);
  return "répondu";
}

async function traiterDecisionAfi(env, stockage, envoyer, decision, numero, historiqueMax, journal) {
  const etat = await stockage.lireEtat();
  const commande = etat.en_attente[numero];
  if (!commande) {
    await envoyer(env.AFI_CHAT_ID, `Aucune commande #${numero} en attente.`);
    return;
  }
  delete etat.en_attente[numero];
  let messageClient;

  if (decision === "OUI") {
    // Le stock a pu bouger depuis la demande : on recalcule avant d'enregistrer.
    const d = devis(etat, commande.zone, commande.lignes.map(({ ref, quantite }) => ({ ref, quantite })));
    if (d.erreur) {
      messageClient = `Bonjour ${commande.client}, désolée : votre commande n°${numero} ne peut plus être honorée (${d.erreur}). Écrivez-nous pour une autre proposition.`;
      await envoyer(env.AFI_CHAT_ID, `Commande #${numero} impossible : ${d.erreur}. Client prévenu.`);
    } else {
      for (const l of d.lignes) etat.produits.find((p) => p.ref === l.ref).stock -= l.quantite;
      etat.commandes.push({ ...commande, ...d, statut: "validée par Afi", validee_le: new Date().toISOString() });
      messageClient = `Bonne nouvelle ${commande.client} ! Votre commande n°${numero} est validée : ${fcfa(d.total)}, livraison à ${d.zone} sous ${etat.delai}. Merci pour votre confiance !`;
      await envoyer(env.AFI_CHAT_ID, `Commande #${numero} enregistrée, stock mis à jour, client prévenu.`);
    }
  } else {
    messageClient = `Bonjour ${commande.client}, désolée : votre commande n°${numero} n'a pas pu être validée par la boutique. Rien n'a été enregistré. N'hésitez pas à nous écrire pour une autre proposition.`;
    await envoyer(env.AFI_CHAT_ID, `Commande #${numero} refusée, client prévenu.`);
  }
  await stockage.ecrireEtat(etat);
  journal({ type: "decision_afi", decision, numero });
  await envoyer(commande.chatId, messageClient);
  await stockage.ajouterAuHistorique(commande.chatId, { role: "assistant", content: messageClient }, historiqueMax);
}
