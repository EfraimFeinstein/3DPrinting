This repository describes parts built for a 3D resin printer.

Parts are described using Python code with the CadQuery library. The main function compiles the part to an STL file. It will always accept a YAML file that describes the settings and the path to an output file as CLI parameters.

The unit of all distances is mm.

All sizes should be expressed as CONSTANTS and the non-derived quantities should be settings that can be set in the YAML settings file. Do not use any magic numbers in the code.

Use "uv" for package management. To install all packages, use `uv sync --all-groups`. To run python, always use `uv run python`.