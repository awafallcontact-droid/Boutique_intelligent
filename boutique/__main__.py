"""Point d'entrée : python -m boutique <commande>

  chat [--equipe] [--palier 1|2]  conversation libre dans le terminal
  palier1                         les 3 tests du palier 1
  palier2                         scénario Afi (refuser puis accepter la validation)
  koffi                           scénario Koffi avec l'équipe multi-agents
  comparer                        tableau agent seul / multi-agents -> docs/comparaison.md
  reset                           remet le stock et les commandes à l'état initial
"""
import argparse
import json
import sys

from . import config
from .donnees import Boutique
from .equipe import Equipe
from .llm import ClientRodium, ErreurLLM
from .trace import Trace
from .validation import est_confirmation
from .vendeur_seul import creer_vendeur_seul


def tour(systeme, historique, message, trace):
    trace.ajouter("client", message)
    historique.append({"role": "user", "content": message})
    reponse = systeme.repondre(historique, client_a_confirme=est_confirmation(message))
    historique.append({"role": "assistant", "content": reponse})
    trace.ajouter("reponse", reponse)
    return reponse


def afficher_etat(boutique):
    boutique._lire()
    print("\n----- data/etat.json -----")
    print("Stock :", {p["ref"]: p["stock"] for p in boutique.produits})
    print("Commandes :", json.dumps(boutique.commandes, ensure_ascii=False, indent=2))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m boutique")
    parser.add_argument("commande", choices=["chat", "palier1", "palier2", "koffi", "comparer", "reset"])
    parser.add_argument("--equipe", action="store_true", help="utiliser l'équipe multi-agents")
    parser.add_argument("--palier", type=int, default=2, choices=[1, 2])
    args = parser.parse_args()

    boutique = Boutique(config.FICHIER_ETAT, config.FICHIER_INITIAL)
    if args.commande == "reset":
        boutique.reinitialiser()
        print("Stock et commandes réinitialisés.")
        return

    llm = ClientRodium()
    trace = Trace()

    if args.commande == "palier1":
        tests = ["Vous avez des pagnes ? Combien ça fait en euros pour ma soeur à Paris ?",
                 "Livrez-moi à Lomé.",
                 "C'est combien le sac en raphia ?"]
        for message in tests:  # chaque test est une conversation neuve
            tour(creer_vendeur_seul(boutique, llm, trace, palier=1), [], message, trace)
            print()
        trace.sauver(config.DOSSIER_TRACES / "palier1.md", "Palier 1 : les 3 tests")

    elif args.commande == "palier2":
        boutique.reinitialiser()
        systeme = Equipe(boutique, llm, trace) if args.equipe else creer_vendeur_seul(boutique, llm, trace)
        historique = []
        print(">>> Au premier « Valider la commande ? », répondez N. Au second, répondez o.\n")
        tour(systeme, historique,
             "Je m'appelle Afi. Je veux 2 robes en wax et 1 sac en raphia, livrés à Calavi.", trace)
        tour(systeme, historique, "Oui, je confirme la commande sans le sac.", trace)
        tour(systeme, historique, "Oui je confirme, merci de réessayer.", trace)
        afficher_etat(boutique)
        trace.sauver(config.DOSSIER_TRACES / f"palier2{'b' if args.equipe else 'a'}_afi.md",
                     "Palier 2 : scénario Afi")

    elif args.commande == "koffi":
        tour(Equipe(boutique, llm, trace), [],
             "Je suis Koffi à Porto-Novo. Combien me coûtent 3 pots de beurre de karité livrés, "
             "et ça fait combien en nairas ?", trace)
        trace.sauver(config.DOSSIER_TRACES / "palier2b_koffi.md", "Palier 2b : scénario Koffi")

    elif args.commande == "comparer":
        from .comparaison import comparer
        print(comparer(llm))

    else:  # chat
        systeme = (Equipe(boutique, llm, trace) if args.equipe
                   else creer_vendeur_seul(boutique, llm, trace, palier=args.palier))
        historique = []
        print("Écrivez comme un client WhatsApp (ligne vide pour quitter).")
        while message := input("\nVous : ").strip():
            tour(systeme, historique, message, trace)
        trace.sauver(config.DOSSIER_TRACES / "chat.md", "Conversation libre")
    print(f"\nAppels LLM : {llm.appels}")


if __name__ == "__main__":
    try:
        main()
    except ErreurLLM as e:
        sys.exit(f"Erreur LLM : {e}")
