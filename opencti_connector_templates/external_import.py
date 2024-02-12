import os
import sys
import time
import urllib3

# from datetime import datetime, timedelta
import datetime

import stix2
from pycti import OpenCTIConnectorHelper


class ExternalImportConnector:
    """Specific external-import connector

    This class encapsulates the main actions, expected to be run by the
    any external-import connector. Note that the attributes defined below
    will be complemented per each connector type.

    Attributes:
        helper (OpenCTIConnectorHelper): The helper to use.
        interval (timedelta): The interval to use.
        update_existing_data (str): Whether to update existing data or not in OpenCTI.
    """

    def __init__(self):

        # The direct access (os.environ[x]) are mandatory,
        # the os.environ.get()s are optional

        if os.environ.get("OPENCTI_SSL_VERIFY", "yes").lower() in ("yes", "true"):
            verify = True
        else:
            verify = False
            urllib3.disable_warnings()

        if os.environ.get("CONNECTOR_UPDATE_EXISTING_DATA", "yes").lower() in (
            "yes",
            "true",
        ):
            self.update_existing_data = True
        else:
            self.update_existing_data = False

        # Initialize the helper class.
        self.helper = OpenCTIConnectorHelper(
            config={
                "OPENCTI_URL": os.environ["OPENCTI_URL"],
                "OPENCTI_TOKEN": os.environ["OPENCTI_TOKEN"],
                "OPENCTI_SSL_VERIFY": verify,
                "CONNECTOR_ID": os.environ["CONNECTOR_ID"],
                "CONNECTOR_TYPE": "EXTERNAL_IMPORT",
                "CONNECTOR_NAME": os.environ["CONNECTOR_NAME"],
                "CONNECTOR_SCOPE": "stix2",
                "CONNECTOR_LOG_LEVEL": os.environ.get("CONNECTOR_LOG_LEVEL", "warning"),
                "CONNECTOR_UPDATE_EXISTING_DATA": self.update_existing_data,
            }
        )
        if not verify:
            self.helper.log_warning(
                "Certificate validation has been disabled, this is not secure."
            )

        # Figure out the interval
        try:
            interval = os.environ["CONNECTOR_RUN_EVERY"]
            timesuffixes = {"d": 60 * 60 * 24, "h": 60 * 60, "m": 60, "s": 1}
            interval = int(interval[:-1]) * timesuffixes[interval[-1].lower()]
            self.interval = datetime.timedelta(seconds=interval)
        except (TypeError, ValueError):
            self.helper.log_error(
                f"Invalid CONNECTOR_RUN_EVERY value, it should be a string like '7d', '2h', '2m' using one of the following suffixes: {', '.join(timesuffixes.keys())}"
            )
            sys.exit(1)

    def _get_env(self, var: str, default: str = "") -> str:
        if val := os.environ.get(var, ""):
            return val

        if not default:
            self.helper.log_warning(f"Missing required environment variable: {var}")
            sys.exit(1)
        else:
            self.helper.log_info(
                f"Missing optional environment variable: {var}, defaulting to '{default}'"
            )
            return default

    def _collect_intelligence(self) -> list:
        """Collect intelligence from the source"""
        raise NotImplementedError

    def run(self) -> None:
        # Main procedure
        self.helper.log_info(f"Starting {self.helper.connect_name} connector...")
        while True:

            run_start = datetime.datetime.utcnow()
            next_run = run_start + self.interval

            try:
                self.current_state = self.helper.get_state()

                # Generate a 'work id' to keep track of progress.
                work_name = f"{self.helper.connect_id} work at {datetime.datetime.utcnow().isoformat()}"
                work_id = self.helper.api.work.initiate_work(
                    self.helper.connect_id, work_name
                )

                try:
                    bundle_objects = self._collect_intelligence()
                    if bundle_objects:
                        bundle = stix2.Bundle(
                            objects=bundle_objects,
                            allow_custom=True,
                        )
                        self.helper.send_stix2_bundle(
                            bundle.serialize(),
                            update=self.update_existing_data,
                            work_id=work_id,
                        )

                except Exception as e:
                    self.helper.api.work.to_processed(
                        work_id,
                        f"Error importing {len(bundle_objects)} STIX2 objects.",
                        in_error=True,
                    )

                # No exception, try-else :-D
                else:
                    self.helper.api.work.to_processed(
                        work_id,
                        f"Succesfully imported {len(bundle_objects)} STIX2 objects.",
                    )

                self.helper.set_state(self.current_state)

            except KeyboardInterrupt:
                break
            except:
                pass

            remaining_time = next_run - datetime.datetime.utcnow()
            if remaining_time.total_seconds() > 0:
                time.sleep(remaining_time.seconds)
            else:
                self.helper.log_warning(
                    f"We're overdue at the end of the run, scheduled start was {int(remaining_time.total_seconds())} ago. Skipping sleep. Check the workload or interval to prevent these warnings."
                )
