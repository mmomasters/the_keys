from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from dataclasses_json import LetterCase, config, dataclass_json


# Common
@dataclass_json
@dataclass
class DatabaseActionDate:
    """Data class for timestamp"""

    date: str
    timezone_type: int
    timezone: str


@dataclass_json
@dataclass
class Info:
    last_seen: datetime = field(metadata=config(
        encoder=datetime.isoformat, decoder=datetime.fromisoformat))
    ip: Optional[str] = field(default=None)


# Accessoire
@dataclass_json
@dataclass
class Accessoire:
    """Data class for accessory"""

    id: int
    id_accessoire: str
    nom: str
    description: Optional[str]
    type: int
    version: int
    type_version: int
    created_at: DatabaseActionDate
    updated_at: DatabaseActionDate
    public_key: str
    info: Info
    configuration: list[Any]
    cfg: Any


# Serrure
@dataclass_json
@dataclass
class SerrureAccessoireAccessoire:
    """Data class for lock accessory"""

    id: int
    id_accessoire: str
    nom: str
    type: int
    version: int
    type_version: int
    info: Info
    configuration: list[Any]


@dataclass_json
@dataclass
class SerrureAccessoire:
    """Data class for lock accessory"""

    id: int
    accessoire: SerrureAccessoireAccessoire
    info: Optional[str]


@dataclass_json
@dataclass
class SerrureProduit:
    """Data class for lock product"""

    id: int
    nom: str
    version: int
    version_beta: int = field(metadata=config(letter_case=LetterCase.CAMEL))


@dataclass_json
@dataclass
class SerrureCompte:
    id: int
    nom: str


@dataclass_json
@dataclass
class SerrureLogData:
    ts: int


@dataclass_json
@dataclass
class SerrureLog:
    id: int
    action_at: DatabaseActionDate
    created_at: DatabaseActionDate
    action: str
    data: SerrureLogData
    status: int
    share_id: Optional[int]
    accessory_share_id: Optional[int]
    utilisateur: str
    utilisateur_id: Optional[int]
    accessoire_id: Optional[int]


@dataclass_json
@dataclass
class Serrure:
    """Data class for lock"""

    id: int
    id_serrure: str
    code: str
    code_serrure: str
    etat: str
    nom: str
    qrcode: str
    serrure_droite: bool
    main_libre: bool
    longitude: int
    latitude: int
    radius: int
    timezone: str
    max_speed: int = field(metadata=config(letter_case=LetterCase.CAMEL))
    latch_delay: int = field(metadata=config(letter_case=LetterCase.CAMEL))
    assisted_actions: bool = field(
        metadata=config(letter_case=LetterCase.CAMEL))
    unlock_only: bool = field(metadata=config(letter_case=LetterCase.CAMEL))
    description: Optional[str]
    version: int
    version_cible: int
    beta: int
    produit: SerrureProduit
    compte: SerrureCompte
    created_at: DatabaseActionDate
    updated_at: DatabaseActionDate
    log_sequence: int = field(metadata=config(letter_case=LetterCase.CAMEL))
    logs: list[SerrureLog]
    public_key: str
    message: str
    accessoires: list[SerrureAccessoire]
    battery: int
    battery_date: DatabaseActionDate
    door: int


# Utilisateur
@dataclass_json
@dataclass
class UtilisateurSerrureUtilisateur:
    username: str
    firstname: str
    lastname: str


@dataclass_json
@dataclass
class UtilisateurSerrureAccessoireAccessoire:
    id: int
    id_accessoire: str
    nom: str
    type: int
    configuration: list[Any]


@dataclass_json
@dataclass
class UtilisateurSerrureAccessoire:
    id: int
    accessoire: UtilisateurSerrureAccessoireAccessoire
    info: Optional[Info]


@dataclass_json
@dataclass
class UtilisateurSerrureProduit:
    id: int
    nom: str
    version: int
    version_beta: int = field(metadata=config(letter_case=LetterCase.CAMEL))


@dataclass_json
@dataclass
class UtilisateurSerrure:
    """Data class for utilisateur"""

    id: int
    id_serrure: str
    code: str
    code_serrure: str
    etat: str
    nom: str
    couleur: Any
    qrcode: str
    serrure_droite: bool
    main_libre: bool
    longitude: int
    latitude: int
    radius: int
    timezone: str
    max_speed: int = field(metadata=config(letter_case=LetterCase.CAMEL))
    latch_delay: int = field(metadata=config(letter_case=LetterCase.CAMEL))
    assisted_actions: bool = field(
        metadata=config(letter_case=LetterCase.CAMEL))
    unlock_only: bool = field(metadata=config(letter_case=LetterCase.CAMEL))
    description: Optional[str]
    log_sequence: int = field(metadata=config(letter_case=LetterCase.CAMEL))
    public_key: str
    message: str
    utilisateur: UtilisateurSerrureUtilisateur
    version: int
    version_cible: int
    beta: int
    battery: int
    battery_date: DatabaseActionDate
    accessoires: list[UtilisateurSerrureAccessoire]
    produit: UtilisateurSerrureProduit


@dataclass_json
@dataclass
class Utilisateur:
    """Data class for utilisateur"""

    id: str
    type: str
    roles: list[str]
    firstname: str
    lastname: str
    locale: str
    username: str
    email: str
    created_at: DatabaseActionDate
    updated_at: DatabaseActionDate
    notification_token: str
    notification_enabled: bool
    serrures: list[UtilisateurSerrure]
    tel: str


# Partage
@dataclass_json
@dataclass
class PartageRole:
    """Data class for share role"""

    id: int
    description: str


@dataclass_json
@dataclass
class PartageUtilisateurUtilisateur:
    """Data class for share user"""

    username: str
    prenom: str
    nom: str
    email: str
    telephone: Optional[str] = None

    def __post_init__(self):
        self.telephone = self.username if self.telephone is None else self.telephone


@dataclass_json
@dataclass
class PartageAccessoireAccessoire:
    """Data class for share accessory"""

    id: int
    id_accessoire: str
    nom: str
    type: int
    version: int
    type_version: int
    configuration: list[Any]


@dataclass_json
@dataclass
class PartageCommun:
    """Data class for abstract share"""

    id: int
    nom: str
    date_debut: Optional[str]
    date_fin: Optional[str]
    heure_debut: Optional[str]
    heure_fin: Optional[str]
    description: Optional[str]
    notification_enabled: bool
    horaires: list[Any]


@dataclass_json
@dataclass
class PartageUtilisateur(PartageCommun):
    """Data class for user share"""

    actif: bool
    role: PartageRole
    utilisateur: PartageUtilisateurUtilisateur


@dataclass_json
@dataclass
class PartageAccessoire(PartageCommun):
    """Data class for accessory share"""

    iddesc: Optional[str]
    nom: str
    actif: bool
    accessoire: PartageAccessoireAccessoire
    code: str


@dataclass_json
@dataclass
class PartageDemandeUtilisateur:
    telephone: str


@dataclass_json
@dataclass
class PartageDemande(PartageCommun):
    role: PartageRole
    code: str
    utilisateur: PartageDemandeUtilisateur


@dataclass_json
@dataclass
class Partage:
    """Data class for share"""

    partages_utilisateur: list[PartageUtilisateur]
    partages_accessoire: list[PartageAccessoire]
    partages_demande: list[PartageDemande]
