"""
Python library to handle the keys api
"""
from __future__ import annotations
from typing import Any, List, TypeVar, Type, Optional
from datetime import datetime, timedelta
import logging
import requests

from .dataclasses import Accessoire, Partage, PartageAccessoire, Utilisateur, UtilisateurSerrureAccessoireAccessoire
from .devices import TheKeysDevice, TheKeysGateway, TheKeysLock
from .errors import (
    NoGatewayIpFoundError,
    NoUtilisateurFoundError,
    NoAccessoriesFoundError,
    NoGatewayAccessoryFoundError,
    GatewayAccessoryNotFoundError,
    NoSharesFoundError,
)

logger = logging.getLogger("the_keyspy")

BASE_URL = "https://api.the-keys.fr"
SHARE_NAME = "TheKeysPy (Remote)"
ACCESSORY_GATEWAY = 1
ACCESSORY_REMOTE = 3

T = TypeVar('T')


def deserialize_dataclass(cls: Type[T], data: Any) -> T:
    """Helper function to deserialize dataclass from dict"""
    if data is None:
        raise ValueError("Cannot deserialize None data")
    return cls.from_dict(data)  # type: ignore


class TheKeysApi:
    """TheKeysApi class"""

    def __init__(
        self, 
        username: str, 
        password: str, 
        gateway_ip: str = '', 
        base_url=BASE_URL,
        rate_limit_delay: float = 5.0,
        rate_limit_delay_light: float = 1.0
    ) -> None:
        self._username = username
        self._password = password
        self._gateway_ip = gateway_ip
        self._base_url = base_url
        self._access_token = None
        self._token_expires_at = None
        self._session = None
        self._rate_limit_delay = rate_limit_delay
        self._rate_limit_delay_light = rate_limit_delay_light

    @property
    def authenticated(self):
        """Return True if the access token exists and has not expired."""
        if not self._access_token:
            return False
        if self._token_expires_at and datetime.now() >= self._token_expires_at:
            self._access_token = None
            return False
        return True

    def find_utilisateur_by_username(self, username: str) -> Utilisateur:
        """Return user matching the passed username"""
        response_data = self.__http_get(f"utilisateur/get/{username}")["data"]
        if response_data is None:
            raise NoUtilisateurFoundError(
                "User could not be retrieved from the API.")
        return deserialize_dataclass(Utilisateur, response_data)

    def find_accessoire_by_id(self, id: int) -> Accessoire:
        """Return accessory matching the passed id"""
        response_data = self.__http_get(f"accessoire/get/{id}")["data"]
        if response_data is None:
            raise GatewayAccessoryNotFoundError(
                "Gateway accessory could not be retrieved from the API.")
        return deserialize_dataclass(Accessoire, response_data)

    def find_partage_by_lock_id(self, lock_id: int) -> Partage:
        """Return share matching the passed lock_id"""
        response_data = self.__http_get(
            f"partage/all/serrure/{lock_id}")["data"]
        if response_data is None:
            raise NoSharesFoundError(
                "No shares found for this lock.")
        return deserialize_dataclass(Partage, response_data)

    def create_accessoire_partage_for_serrure_id(
        self, serrure_id: int, share_name: str, accessoire: UtilisateurSerrureAccessoireAccessoire
    ) -> PartageAccessoire:
        """Create a share for the passed serrure_id and accessoire"""
        data = {}
        data["partage_accessoire[description]"] = ""
        data["partage_accessoire[nom]"] = share_name
        data["partage_accessoire[iddesc]"] = "remote"

        response = self.__http_post(
            f"partage/create/{serrure_id}/accessoire/{accessoire.id_accessoire}", data)["data"]
        partage_accessoire = {}
        partage_accessoire["id"] = response["id"]
        partage_accessoire["iddesc"] = "remote"
        partage_accessoire["nom"] = share_name
        partage_accessoire["actif"] = True
        partage_accessoire["date_debut"] = None
        partage_accessoire["date_fin"] = None
        partage_accessoire["heure_debut"] = None
        partage_accessoire["heure_fin"] = None
        partage_accessoire["description"] = None
        partage_accessoire["notification_enabled"] = True
        partage_accessoire["accessoire"] = accessoire
        partage_accessoire["horaires"] = []
        partage_accessoire["code"] = response["code"]
        return deserialize_dataclass(PartageAccessoire, partage_accessoire)

    def get_locks(self) -> List[TheKeysLock]:
        return list(device for device in self.get_devices() if isinstance(device, TheKeysLock))

    def get_gateways(self) -> List[TheKeysGateway]:
        return list(device for device in self.get_devices() if isinstance(device, TheKeysGateway))

    def get_devices(self, share_name=SHARE_NAME) -> List[TheKeysDevice]:
        """Return all devices"""
        devices = []
        user = self.find_utilisateur_by_username(self._username)

        # Return empty list if user has no locks
        if not user.serrures:
            return []

        serrures_with_accessoires = [serrure for serrure in user.serrures if hasattr(
            serrure, 'accessoires') and serrure.accessoires]
        if not serrures_with_accessoires:
            raise NoAccessoriesFoundError(
                "No accessories found for this user.")

        # Cache gateway instances by host so all locks share ONE gateway object per physical device.
        # This ensures the rate limiter is shared across all locks on the same gateway,
        # preventing simultaneous requests that overwhelm the hardware.
        gateway_cache: dict[str, TheKeysGateway] = {}

        for serrure in serrures_with_accessoires:
            accessoire = None
            gateway = None

            if self._gateway_ip != '':
                # Manual IP provided, use first gateway accessory without checking info
                gateway_accessoires = list(
                    filter(lambda x: x.accessoire.type == ACCESSORY_GATEWAY, serrure.accessoires))
                if gateway_accessoires:
                    accessoire = gateway_accessoires[0]
                    # Reuse cached gateway for this IP if already created
                    if self._gateway_ip not in gateway_cache:
                        gateway_cache[self._gateway_ip] = TheKeysGateway(
                            1,
                            self._gateway_ip,
                            rate_limit_delay=self._rate_limit_delay,
                            rate_limit_delay_light=self._rate_limit_delay_light,
                        )
                        devices.append(gateway_cache[self._gateway_ip])
                    gateway = gateway_cache[self._gateway_ip]

            if not accessoire:
                # No manual IP or accessoire not found - fetch gateway info from API
                gateway_accessoires = filter(
                    lambda x: x.accessoire.type == ACCESSORY_GATEWAY, serrure.accessoires)

                # Collect all valid gateways (seen in last 10 minutes) and select the most recent
                valid_gateways = [(gw, x) for x in gateway_accessoires if (gw := self.find_accessoire_by_id(
                    x.accessoire.id)) and gw.info and gw.info.last_seen > datetime.now() - timedelta(minutes=10)]

                if not valid_gateways:
                    raise NoGatewayAccessoryFoundError(
                        "No gateway accessory found for this lock.")

                # Select the most recently seen gateway
                gateway_accessoire, accessoire = max(
                    valid_gateways, key=lambda g: g[0].info.last_seen)

                gateway_ip = gateway_accessoire.info.ip if gateway_accessoire.info.ip else None
                if not gateway_ip:
                    raise NoGatewayIpFoundError("No gateway IP found.")

                # Reuse cached gateway for this IP if already created
                if gateway_ip not in gateway_cache:
                    gateway_cache[gateway_ip] = TheKeysGateway(
                        gateway_accessoire.id,
                        gateway_ip,
                        rate_limit_delay=self._rate_limit_delay,
                        rate_limit_delay_light=self._rate_limit_delay_light,
                    )
                    devices.append(gateway_cache[gateway_ip])
                gateway = gateway_cache[gateway_ip]

            partages_accessoire = self.find_partage_by_lock_id(
                serrure.id).partages_accessoire
            if not partages_accessoire:
                partages_accessoire = []

            partage = next((x for x in partages_accessoire if x.nom ==
                           SHARE_NAME and x.accessoire.id == accessoire.accessoire.id), None)
            if partage is None:
                partage = self.create_accessoire_partage_for_serrure_id(
                    serrure.id, share_name, accessoire.accessoire)

            devices.append(TheKeysLock(serrure.id, gateway,
                           serrure.nom, serrure.id_serrure, partage.code))

        return devices

    def __http_request(self, method: str, url: str, data: Any = None):
        if not self.authenticated:
            self.__authenticate()

        full_url = f"{self._base_url}/fr/api/v2/{url}"
        headers = {"Authorization": f"Bearer {self._access_token}"}

        logger.debug("%s %s", method.upper(), full_url)
        if method.lower() == "get":
            response = requests.get(full_url, headers=headers)
        elif method.lower() == "post":
            response = requests.post(full_url, headers=headers, data=data)
        else:
            raise ValueError(f"HTTP method non supportée : {method}")

        if response.status_code != 200:
            raise RuntimeError(response.text)

        json_data = response.json()
        logger.debug("response_data: %s", json_data)
        return json_data

    def __http_get(self, url: str):
        return self.__http_request("get", url)

    def __http_post(self, url: str, data: Any):
        return self.__http_request("post", url, data)

    def __authenticate(self):
        # REST API authentication
        response = requests.post(
            f"{self._base_url}/api/login_check",
            data={"_username": self._username, "_password": self._password},
        )

        if response.status_code != 200:
            raise RuntimeError(response.text)

        json = response.json()
        self._access_token = json["access_token"]
        expires_in = json.get("expires_in", 3600)
        # Subtract 60s buffer so we refresh before the server rejects the token
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

    def __authenticate_session(self):
        """Create a session for account-based actions (like reboot)."""
        if self._session is None:
            self._session = requests.Session()
        
        login_url = f"{self._base_url}/auth/fr/login_check"
        login_data = {"_username": self._username, "_password": self._password}
        
        response = self._session.post(login_url, data=login_data)
        if response.status_code != 200:
            # Check for redirect to login page (302) which requests.Session follows by default.
            # If the final URL is still a login page, it failed.
            if "login" in response.url:
                raise RuntimeError("Session authentication failed")
        
        return self._session

    def reboot_gateway(self, accessory_id: int) -> bool:
        """Reboot the gateway via the cloud API."""
        # If the ID is 1, it's a dummy ID from a manual setup.
        # We need the real cloud ID to reboot via the portal.
        if accessory_id == 1:
            logger.debug("Gateway ID is 1 (local-only), searching for real cloud ID...")
            try:
                user = self.find_utilisateur_by_username(self._username)
                gateways = []
                for serrure in user.serrures:
                    if hasattr(serrure, 'accessoires'):
                        gateways.extend([a.accessoire.id for a in serrure.accessoires 
                                       if a.accessoire.type == ACCESSORY_GATEWAY])
                if gateways:
                    accessory_id = gateways[0]
                    logger.debug("Found real cloud ID: %s", accessory_id)
                else:
                    logger.error("Could not find any gateway ID in your account")
                    return False
            except Exception as e:
                logger.error("Error finding real gateway ID: %s", e)
                return False

        session = self.__authenticate_session()
        reboot_url = f"{self._base_url}/fr/compte/accessoire/{accessory_id}/reboot"
        
        try:
            # This is a GET request in the web interface
            response = session.get(reboot_url)
            # A successful reboot redirects to the accessory view page
            if response.status_code == 200 and f"/accessoire/{accessory_id}/view" in response.url:
                logger.info("Successfully triggered reboot for gateway %s", accessory_id)
                return True
            
            # If redirected back to login, retry authentication once
            if "login" in response.url:
                self._session = None
                session = self.__authenticate_session()
                response = session.get(reboot_url)
                if response.status_code == 200 and f"/accessoire/{accessory_id}/view" in response.url:
                    return True
                    
            logger.error("Failed to reboot gateway %s: %s (Final URL: %s)", 
                        accessory_id, response.status_code, response.url)
            return False
        except Exception as err:
            logger.error("Error during gateway reboot: %s", err)
            return False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        if exception_type is not None:
            print(exception_type, exception_value)

        return True
