# -*- coding: utf-8 -*-
"""CLI command to parse CIF files that were scraped from AMCSD into ``CifData`` nodes."""
from aiida.cmdline.params.types import GroupParamType
import click

from .cli import cli


@click.option(
    '-F',
    '--group-cif-file',
    type=GroupParamType(create_if_not_exist=True),
    required=True,
    help='Group containing the scraped CIF files.'
)
@click.option(
    '-D',
    '--group-cif-data',
    type=GroupParamType(create_if_not_exist=True),
    required=True,
    help='Group to store the parsed ``CifData`` nodes in.'
)
@click.option('-M', '--max-number', type=click.INT, required=False, help='Limit the number of CIF files to parse.')
@click.option('-n', '--dry-run', is_flag=True, help='Perform a dry-run and do not store any provenance.')
@cli.command('parse')
def cmd_parse(group_cif_file, group_cif_data, max_number, dry_run):
    """Parse CIF files scraped from AMCSD into ``CifData`` nodes."""
    # pylint: disable=too-many-locals
    from aiida.cmdline.utils import echo
    from aiida.orm import CalcFunctionNode, CifData, Group, QueryBuilder, SinglefileData

    from aiida_amcsd.calculations.functions.cif_file_to_cif_data import cif_file_to_cif_data

    # Determine nodes from input group that haven't already been parsed.
    query = QueryBuilder()
    query.append(Group, filters={'id': group_cif_file.pk}, tag='group')
    query.append(SinglefileData, with_group='group', tag='cif_file', project='id')
    query.append(CalcFunctionNode, with_incoming='cif_file', tag='calcfunction')
    query.append(CifData, with_incoming='calcfunction')
    parsed_ids = set(query.all(flat=True))

    query = QueryBuilder()
    query.append(Group, filters={'id': group_cif_file.pk}, tag='group')
    query.append(SinglefileData, with_group='group', filters={'id': {'!in': parsed_ids}} if parsed_ids else {})
    query.limit(max_number)

    cif_count = query.count()
    cif_datas = []
    bar_template = '%(label)-50s [%(bar)s] %(info)s'

    if cif_count == 0:
        echo.echo_report('no CIF files to parse.')
        return

    echo.echo_report(f'found {cif_count} CIF files to parse.')

    with click.progressbar(query.all(flat=True), width=0, bar_template=bar_template) as iterator:
        for cif_file in iterator:

            iterator.label = click.style('Parsing: ', fg='blue', bold=True) + f'{cif_file.filename}<{cif_file.pk}>'

            try:
                results = cif_file_to_cif_data.run(cif_file, metadata={'store_provenance': not dry_run})
            except Exception as exception:  # pylint: disable=broad-except
                echo.echo_error(f'failed to parse SinglefileData<{cif_file.uuid}>: {exception}')
            else:
                cif_datas.append(results['cif_data'])

    echo.echo_success('parsing completed, adding parsed nodes to group.')
    if not dry_run:
        group_cif_data.add_nodes(cif_datas)

    echo.echo_success(f'added {len(cif_datas)} nodes to `{group_cif_data}`.')
