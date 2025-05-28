"""Coordinator for MELCloud integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import cast

from aiohttp import ClientConnectionError, ClientResponseError
from pymelcloud import get_devices

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .device import MelCloudDevice

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=15)


class MelCloudDataUpdateCoordinator(
    DataUpdateCoordinator[dict[str, list[MelCloudDevice]]]
):
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
                self.hass, cast(ConfigEntry, self.config_entry).data[CONF_TOKEN]
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
                await device.async_update()

        return self.data
