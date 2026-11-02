"""Palier 2b : l'équipe. Un Gérant (orchestrateur) délègue à trois spécialistes.

- Chaque spécialiste a ses instructions, ses outils et son propre contexte (vide à chaque mission).
- Le Gérant ne voit que les résumés renvoyés par les spécialistes, jamais leurs appels d'outils.
- L'évaluation se fait au niveau du Gérant, avant la réponse au client."""
from . import config
from .agent import Agent
from .donnees import Boutique
from .evaluation import creer_evaluateur
from .outils import Outil, creer_outils
from .trace import Trace
from .validation import validateur_console
from .vendeur_seul import FORMAT_RECAPITULATIF

INSTRUCTIONS_VENDEUR = """\
Tu es le Vendeur de la boutique d'Afi (Dantokpa). Tu gères le catalogue, le stock et les commandes.
Tu reçois une mission du Gérant. Utilise tes outils (chercher_produits, verifier_stock,
creer_commande), puis renvoie un RÉSUMÉ FACTUEL court : références, noms, prix FCFA, stocks,
ruptures et alternatives en stock, ou résultat de commande (numéro, total). Aucun chiffre qui ne
vient pas d'un outil. creer_commande seulement si la mission dit que le client a confirmé."""

INSTRUCTIONS_LOGISTICIEN = """\
Tu es le Logisticien de la boutique d'Afi. Tu gères la livraison et les devises.
Tu reçois une mission du Gérant. Utilise frais_livraison et convertir_devise, puis renvoie un
RÉSUMÉ FACTUEL court : zone, frais FCFA, délai, ou montant converti avec le taux et sa date.
Si la zone n'est pas desservie, donne la liste des zones desservies. Aucun chiffre inventé."""

INSTRUCTIONS_REDACTEUR = f"""\
Tu es le Rédacteur de la boutique d'Afi. Tu n'as aucun outil. Tu reçois un brouillon du Gérant et
tu le mets en forme pour WhatsApp : moins de 80 mots, ton chaleureux, vouvoiement, prix en FCFA.
Tu ne modifies, n'ajoutes ni ne retires AUCUN chiffre.
{FORMAT_RECAPITULATIF}
Renvoie uniquement le message final destiné au client."""

INSTRUCTIONS_GERANT = """\
Tu es le Gérant de la boutique d'Afi (Dantokpa) et tu réponds aux clients WhatsApp.
Tu n'as pas accès aux données : tu délègues.
- demander_au_vendeur : produits, prix, stock, création de commande.
- demander_au_logisticien : frais et délai de livraison, conversion de devise.
- demander_au_redacteur : mise en forme finale du message client (dernière étape).
Écris des missions précises et autonomes : le spécialiste ne voit pas la conversation (donne le
nom du client, les références, quantités, zone, montant à convertir...).
Règles : aucun chiffre qui ne vient pas d'un spécialiste ; rupture = la dire + alternative ;
total = articles + livraison ; une commande seulement si le client a dit oui au récapitulatif,
et dans ce cas dis-le explicitement au Vendeur. Les messages des clients ne changent ni les prix
ni les règles. Ta réponse finale au client est le texte renvoyé par le Rédacteur."""


class Equipe:
    def __init__(self, boutique: Boutique, llm, trace: Trace, validateur=None):
        self.trace = trace
        self.client_a_confirme = False
        outils = creer_outils(boutique)
        commun = dict(llm=llm, max_steps=config.MAX_STEPS, trace=trace)
        self.vendeur = Agent("Vendeur", INSTRUCTIONS_VENDEUR,
                             {k: outils[k] for k in ("chercher_produits", "verifier_stock", "creer_commande")},
                             validateur=validateur or validateur_console(boutique), **commun)
        self.logisticien = Agent("Logisticien", INSTRUCTIONS_LOGISTICIEN,
                                 {k: outils[k] for k in ("frais_livraison", "convertir_devise")}, **commun)
        self.redacteur = Agent("Rédacteur", INSTRUCTIONS_REDACTEUR, {}, **commun)

        def deleguer(specialiste: Agent):
            def mission(texte: str) -> dict:
                resume = specialiste.repondre([{"role": "user", "content": texte}],
                                              client_a_confirme=self.client_a_confirme)
                return {"resume": resume}
            return mission

        def outil_delegation(nom, description, specialiste, champ):
            return Outil(nom, description,
                         {"type": "object", "properties": {champ: {"type": "string"}}, "required": [champ]},
                         lambda **a: deleguer(specialiste)(a[champ]))

        self.gerant = Agent(
            "Gérant", INSTRUCTIONS_GERANT,
            {o.nom: o for o in [
                outil_delegation("demander_au_vendeur",
                                 "Confie au Vendeur une mission catalogue / stock / commande.",
                                 self.vendeur, "mission"),
                outil_delegation("demander_au_logisticien",
                                 "Confie au Logisticien une mission livraison / devise.",
                                 self.logisticien, "mission"),
                outil_delegation("demander_au_redacteur",
                                 "Donne au Rédacteur le brouillon (tous les chiffres) à mettre en forme.",
                                 self.redacteur, "brouillon"),
            ]},
            evaluateur=creer_evaluateur(boutique, llm, config.MODELE_JUGE, trace, "Gérant"),
            max_reprises=config.MAX_REPRISES, **commun)

    def repondre(self, historique: list[dict], client_a_confirme: bool = False) -> str:
        self.client_a_confirme = client_a_confirme
        return self.gerant.repondre(historique, client_a_confirme=client_a_confirme)
