# -*- coding: utf-8 -*-
"""Command line interface for ``aiida-amcsd``."""
from aiida.cmdline.params import options, types
import click


@click.group()
@options.PROFILE(type=types.ProfileParamType(load_profile=True), expose_value=False)
def cli():
    """Command line interface to scrape, import and clean CIF files from the AMCSD into AiiDA."""
