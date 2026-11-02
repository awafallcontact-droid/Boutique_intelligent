"""Configuration lue dans l'environnement (fichier .env). Aucune clé dans le code."""
import os
from pathlib import Path

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent
load_dotenv(RACINE / ".env")

RODIUM_API_KEY = os.getenv("RODIUM_API_KEY", "")
RODIUM_BASE_URL = os.getenv("RODIUM_BASE_URL", "https://api.rodiumai.io/v1")
MODELE = os.getenv("MODELE", "anthropic/claude-haiku-5-5")
MODELE_JUGE = os.getenv("MODELE_JUGE", MODELE)

# Garde-fous de la boucle
MAX_STEPS = int(os.getenv("MAX_STEPS", "8"))
MAX_REPRISES = int(os.getenv("MAX_REPRISES", "2"))

# Données
FICHIER_INITIAL = RACINE / "data" / "boutique_initiale.json"
FICHIER_ETAT = Path(os.getenv("FICHIER_ETAT", str(RACINE / "data" / "etat.json")))

# API de taux réelle, sans clé (ExchangeRate-API, accès ouvert), base XOF = FCFA
API_CHANGE_URL = os.getenv("API_CHANGE_URL", "https://open.er-api.com/v6/latest/XOF")

DOSSIER_TRACES = RACINE / "docs" / "traces"
