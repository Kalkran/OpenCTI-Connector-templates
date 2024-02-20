import base64
import datetime
import pika
import ssl
import json
import logging
import urllib3
import os
from typing import Any
import stix2

import pycti

logger = logging.getLogger(__name__)


def _env() -> callable:
    """Returns a function that can be used to query the environment."""
    environment = os.environ.copy()
    # See if we can update the environment from a '.env'-file. Ignoring any errors if the file isn't there or accessible.
    try:
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                environment.update({key: value})
    except:
        pass

    def bool_(b: str) -> bool:
        """Create a bool from a string"""
        if type(b) is bool:
            return b
        return b.lower() in ("yes", "y", "true", "1")

    def get_variable(envvar: str, default: str = "", type_: type = str) -> Any:
        """Query the environment for a variable.

        If no default is provided and the key is not present in the environment, an exception will be raised.
        """
        if type_ == bool:
            type_ = bool_

        if envvar in environment.keys():
            return type_(environment[envvar])
        if default:
            return type_(default)

        raise ValueError(
            f"Missing environment variable {envvar}. No default was provided."
        )

    return get_variable


class OCTIConnectorHelper:

    log_debug = logger.debug
    log_info = logger.info
    log_warn = logger.warn
    log_error = logger.error

    env = _env()

    def __init__(
        self,
        # Mandatory arguments__________
        opencti_url: str = env("OPENCTI_URL"),
        opencti_token: str = env("OPENCTI_TOKEN"),
        connector_id: str = env("CONNECTOR_ID"),
        connector_type: pycti.ConnectorType = env(
            "CONNECTOR_TYPE", type_=pycti.ConnectorType
        ),
        connector_name: str = env("CONNECTOR_NAME"),
        # TODO: Ideally we would like to scope.split(",") this and work with a list,
        # but this is hidden inside pycti.OpenCTIConnector.__init__()
        connector_scope: list[str] = env("CONNECTOR_SCOPE", ""),
        # Optional arguments_____________
        opencti_ssl_verify: bool = env("OPENCTI_SSL_VERIFY", True, bool),
    ) -> None:
        pass

        self.opencti_url = opencti_url
        self.opencti_token = opencti_token
        self.opencti_ssl_verify = opencti_ssl_verify

        if not self.opencti_ssl_verify:
            logger.warn(
                "OpenCTI HTTPS certificate validation is turned off. "
                + "If you're having certificate issues, it would be better to add the certificate to the Python certifi file "
                + "(python3 -m certifi for the path). "
            )
            logger.warn("Turning off certificate validation errors.")
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.connector = pycti.OpenCTIConnector(
            connector_id,
            connector_name,
            connector_type,
            connector_scope,
            False,  # auto?
            False,  # only_contextual?
            False,  # playbook_compatible?
        )

        self.api = pycti.OpenCTIApiClient(
            self.opencti_url,
            self.opencti_token,
            ssl_verify=self.opencti_ssl_verify,
        )

        # Register the connector in OpenCTI.
        self.connector_configuration = self.api.connector.register(self.connector)
        logger.info(f"Registered the connector in OpenCTI ({self.connector.id})")

    def get_state(self) -> dict:
        """Returns the stored connector state"""
        return json.loads(self.connector_configuration["connector_state"])

    def set_state(self, state: dict) -> dict:
        """Stores the connector state"""
        self.connector_configuration["connector_state"] = json.dumps(state)
        self.api.connector.ping(self.connector.id, state)
        return state

    def send_stix2_bundle(
        self, bundle: stix2.Bundle, work_name: str = "", update: bool = True
    ) -> list:
        """Sends a STIX2 Bundle to OpenCTI

        Creates "work" with expectations and will report finished."""

        if not bundle:
            return []

        if not work_name:
            work_name = (
                f"{self.connector.name}-{datetime.datetime.utcnow().isoformat()}"
            )
        work_id = self.api.work.initiate_work(self.connector.id, work_name)

        # TODO: Investigate why we do this..
        # https://github.com/OpenCTI-Platform/client-python/blob/master/pycti/connector/opencti_connector_helper.py#L1014
        # Maybe reduces size or something?

        bundles = pycti.OpenCTIStix2Splitter().split_bundle(
            bundle.serialize(), use_json=True
        )

        self.api.work.add_expectations(work_id, len(bundles))

        rabbitmq_connection = self._get_pika_connection()
        rabbitmq_channel = rabbitmq_connection.channel()

        # https://github.com/OpenCTI-Platform/client-python/blob/master/pycti/connector/opencti_connector_helper.py#L1047
        for i, bundle in enumerate(bundles, start=1):
            self.log_warn(f"Sending bundle #{i}/{len(bundles)}")
            self._send_bundle(rabbitmq_channel, bundle, work_id, i, update)

        rabbitmq_channel.close()
        rabbitmq_connection.close()

        return bundles

    def _get_pika_connection(self) -> pika.BlockingConnection:
        return pika.BlockingConnection(
            pika.ConnectionParameters(
                self.connector_configuration["config"]["connection"]["host"],
                self.connector_configuration["config"]["connection"]["port"],
                self.connector_configuration["config"]["connection"]["vhost"],
                pika.PlainCredentials(
                    self.connector_configuration["config"]["connection"]["user"],
                    self.connector_configuration["config"]["connection"]["pass"],
                ),
                # https://github.com/OpenCTI-Platform/client-python/blob/master/pycti/connector/opencti_connector_helper.py#L1032
                # ssl_options=pika.SSLOptions(
                #     (
                #         ssl.create_default_context()
                #         if self.opencti_ssl_verify
                #         else ssl._create_unverified_context()
                #     ),
                #     self.connector_configuration["config"]["connection"]["host"],
                # ),
            )
        )

    def _send_bundle(
        self,
        channel: "pika.adapter.blocking_connection.BlockingChannel",
        bundle: stix2.Bundle,
        work_id: str,
        sequence: int,
        update: bool = True,
    ) -> None:
        message = {
            "applicant_id": self.connector_configuration["connector_user_id"],
            "action_sequence": sequence,
            "entities_types": [],
            "content": base64.b64encode(bundle.encode("utf-8", "escape")).decode(
                "utf-8"
            ),
            "update": update,
        }

        # Send the message
        try:
            channel.basic_publish(
                exchange=self.connector_configuration["config"]["push_exchange"],
                routing_key=self.connector_configuration["config"]["push_routing"],
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2, content_encoding="utf-8"  # make message persistent
                ),
            )
            self.log_debug("Bundle has been sent")
        except (pika.exceptions.UnroutableError, pika.exceptions.NackError):
            # TODO: Fix this?
            # Why would you retry without changing anything..?!
            # https://github.com/OpenCTI-Platform/client-python/blob/master/pycti/connector/opencti_connector_helper.py#L1112
            self.log_error("Unable to send bundle, retry...")
            self._send_bundle(channel, bundle, work_id, sequence, update)
