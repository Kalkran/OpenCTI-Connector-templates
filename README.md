

# OpenCTI Connector templates

This repository contains modified versions of the OpenCTI Connector templates that can be found on their Github: https://github.com/OpenCTI-Platform/connectors in the `templates/`-folder.

It aims to correct some issues that are found in the default templates and provide a PyPi package for easy re-use in other implementations.


### Issues

#### Overall

 - Unclear usage of environment variables (mostly caused by the underlying `pycti` package)


#### External Import

 - Logging is too verbose and in an unclear format.
 - Empty result sets throw an exception