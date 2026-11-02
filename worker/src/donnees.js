// Catalogue, zones et calcul du total : la même logique que boutique/donnees.py.

export const ETAT_INITIAL = {
  produits: [
    { ref: "P01", nom: "Pagne wax 6 yards", prix: 12000, stock: 14 },
    { ref: "P02", nom: "Chemise bazin homme", prix: 18500, stock: 3 },
    { ref: "P03", nom: "Sac en raphia", prix: 7500, stock: 0 },
    { ref: "P04", nom: "Sandales en cuir", prix: 9000, stock: 8 },
    { ref: "P05", nom: "Robe en wax", prix: 22000, stock: 5 },
    { ref: "P06", nom: "Beurre de karité 500 g", prix: 3500, stock: 40 },
  ],
  zones: { Cotonou: 1000, Akpakpa: 1000, "Fidjrossè": 1500, Calavi: 2000, "Porto-Novo": 3000, Ouidah: 3500 },
  delai: "24 à 48 h",
  commandes: [],
  en_attente: {}, // commandes confirmées par le client, en attente de la décision d'Afi
  prochain_numero: 1,
};

export function normaliser(texte) {
  return String(texte).normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/-/g, " ").split(/\s+/).filter(Boolean).join(" ");
}

export function fcfa(n) {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " FCFA";
}

export function produit(etat, ref) {
  return etat.produits.find((p) => p.ref === String(ref).trim().toUpperCase()) ?? null;
}

export function trouverZone(etat, nom) {
  const cible = normaliser(nom);
  const officiel = Object.keys(etat.zones).find((z) => normaliser(z) === cible);
  return officiel ? { zone: officiel, frais: etat.zones[officiel] } : null;
}

export function devis(etat, zone, articles) {
  const z = trouverZone(etat, zone ?? "");
  if (!z) return { erreur: "zone non desservie", zones_desservies: Object.keys(etat.zones) };
  if (!articles?.length) return { erreur: "aucun article" };
  const lignes = [];
  for (const a of articles) {
    const p = produit(etat, a.ref ?? "");
    if (!p) return { erreur: `référence inconnue : ${a.ref}` };
    const q = Number.parseInt(a.quantite, 10);
    if (!(q >= 1)) return { erreur: `quantité invalide pour ${p.nom}` };
    if (q > p.stock) return { erreur: `stock insuffisant pour ${p.nom}`, stock_disponible: p.stock };
    lignes.push({ ref: p.ref, nom: p.nom, quantite: q, prix_unitaire: p.prix, montant: q * p.prix });
  }
  const sousTotal = lignes.reduce((s, l) => s + l.montant, 0);
  return { lignes, zone: z.zone, frais_livraison: z.frais, sous_total: sousTotal,
           total: sousTotal + z.frais, delai: etat.delai };
}
