"""Trace lisible : chaque appel d'outil, ses arguments, son résultat, chaque verdict."""
import json
from pathlib import Path

SYMBOLES = {"client": "CLIENT  ", "outil": "OUTIL   ", "resultat": "  <-    ", "eval": "EVAL    ",
            "validation": "AFI     ", "reponse": "REPONSE ", "limite": "LIMITE  ", "info": "INFO    "}


class Trace:
    def __init__(self, afficher: bool = True):
        self.afficher = afficher
        self.lignes: list[str] = []

    def ajouter(self, type_: str, texte: str, agent: str = "", etape: int | None = None):
        prefixe = SYMBOLES.get(type_, type_)
        contexte = f"[{agent}{f' · étape {etape}' if etape else ''}] " if agent else ""
        ligne = f"{prefixe}{contexte}{texte}"
        self.lignes.append(ligne)
        if self.afficher:
            print(ligne, flush=True)

    def outil(self, agent, etape, nom, arguments, resultat):
        self.ajouter("outil", f"{nom}({json.dumps(arguments, ensure_ascii=False)})", agent, etape)
        self.ajouter("resultat", json.dumps(resultat, ensure_ascii=False))

    def sauver(self, chemin: Path, titre: str):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(f"# {titre}\n\n```text\n" + "\n".join(self.lignes) + "\n```\n", encoding="utf-8")
