"""Coordinator for MELCloud integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from aiohttp import ClientConnectionError, ClientResponseError
from pymelcloud import Device, get_devices
from pymelcloud.atw_device import Zone

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=15)


class MelCloudDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Coordinator for MELCloud data updates."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=MIN_TIME_BETWEEN_UPDATES,
        )
        self._session = async_get_clientsession(hass)

    async def _mel_devices_setup(
        self, hass: HomeAssistant, token: str
    ) -> dict[str, list[MelCloudDevice]]:
        """Query connected devices from MELCloud."""
        session = async_get_clientsession(hass)
        async with asyncio.timeout(10):
            all_devices = await get_devices(
                token=token,
                session=session,
                conf_update_interval=timedelta(minutes=30),
                device_set_debounce=timedelta(seconds=2),
            )
        wrapped_devices: dict[str, list[MelCloudDevice]] = {}
        for device_type, devices in all_devices.items():
            wrapped_devices[device_type] = [
                MelCloudDevice(device) for device in devices
            ]
        return wrapped_devices

    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        try:
            mel_devices = await self._mel_devices_setup(
                self.hass, self.config_entry.data[CONF_TOKEN]
            )
        except ClientResponseError as ex:
            if isinstance(ex, ClientResponseError) and ex.code == 401:
                raise ConfigEntryAuthFailed from ex
            raise ConfigEntryNotReady from ex
        except (TimeoutError, ClientConnectionError) as ex:
            raise ConfigEntryNotReady from ex

        _LOGGER.debug("MELCloud devices found: %s", mel_devices)
        self.data = mel_devices

    async def _async_update_data(self):
        """Fetch data from MELCloud."""
        _LOGGER.debug("Updating MELCloud devices")

        for device_list in self.data.values():
            for device in device_list:
                try:
                    await device.async_update()
                except Exception as ex:  # TODO: refine exception handling
                    _LOGGER.error("Error updating device %s: %s", device.name, ex)
        return self.data


class MelCloudDevice:
    """MELCloud Device instance."""

    def __init__(self, device: Device) -> None:
        """Construct a device wrapper."""
        self.device = device
        self.name = device.name
        self._available = True

    async def async_update(self, **kwargs):
        """Pull the latest data from MELCloud."""
        try:
            await self.device.update()
            self._available = True
        except ClientConnectionError:
            _LOGGER.warning("Connection failed for %s", self.name)
            self._available = False

    async def async_set(self, properties: dict[str, Any]):
        """Write state changes to the MELCloud API."""
        try:
            await self.device.set(properties)
            self._available = True
        except ClientConnectionError:
            _LOGGER.warning("Connection failed for %s", self.name)
            self._available = False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def device_id(self):
        """Return device ID."""
        return self.device.device_id

    @property
    def building_id(self):
        """Return building ID of the device."""
        return self.device.building_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return a device description for device registry."""
        model = None
        if (unit_infos := self.device.units) is not None:
            model = ", ".join([x["model"] for x in unit_infos if x["model"]])
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self.device.mac)},
            identifiers={(DOMAIN, f"{self.device.mac}-{self.device.serial}")},
            manufacturer="Mitsubishi Electric",  # TODO: put this in const.py
            model=model,
            name=self.name,
        )

    def zone_device_info(self, zone: Zone) -> DeviceInfo:
        """Return a zone device description for device registry."""
        dev = self.device
        return DeviceInfo(
            identifiers={(DOMAIN, f"{dev.mac}-{dev.serial}-{zone.zone_index}")},
            manufacturer="Mitsubishi Electric",  # TODO: put this in const.py
            name=f"{self.name} {zone.name}",
            via_device=(DOMAIN, f"{dev.mac}-{dev.serial}"),
        )
