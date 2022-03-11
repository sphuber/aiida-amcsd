# -*- coding: utf-8 -*-
"""CLI command to clean ``CifData`` nodes using the ``CifCleanWorkChain`` of ``aiida-codtools``."""
from aiida.cmdline.params import types
import click

from .cli import cli


@click.option(
    '-D',
    '--group-cif-data',
    type=types.GroupParamType(create_if_not_exist=False),
    required=True,
    help='Group containing the ``CifData`` nodes to be cleaned.'
)
@click.option(
    '-C',
    '--group-cif-clean',
    type=types.GroupParamType(create_if_not_exist=True),
    required=True,
    help='Group to store the cleaned ``CifData`` nodes into.'
)
@click.option(
    '-W',
    '--group-cif-workchain',
    type=types.GroupParamType(create_if_not_exist=True),
    required=True,
    help='Group to store the ``CifCleanWorkChain`` nodes into.'
)
@click.option(
    '-S',
    '--group-cif-structure',
    type=types.GroupParamType(create_if_not_exist=True),
    help='Group to store the ``StructureData`` nodes, parsed from the cleaned ``CifData`` nodes, into.'
)
@click.option(
    '-F',
    '--cif-filter',
    required=True,
    type=types.CodeParamType(entry_point='codtools.cif_filter'),
    help='Code that references the codtools cif_filter script.'
)
@click.option(
    '-X',
    '--cif-select',
    required=True,
    type=types.CodeParamType(entry_point='codtools.cif_select'),
    help='Code that references the codtools cif_select script.'
)
@click.option('--concurrent', type=click.INT, default=100, help='Number of maximum concurrent work chains to submit.')
@click.option('--interval', type=click.INT, default=30, help='Number of seconds to sleep after a submit round.')
@cli.command('clean')
def cmd_clean(
    group_cif_data, group_cif_clean, group_cif_structure, group_cif_workchain, cif_filter, cif_select, concurrent,
    interval
):
    """Clean ``CifData`` nodes using the ``CifCleanWorkChain``.

    The ``CifCleanWorkChain`` is provided by the ``aiida-codtools`` plugin. It will use ``cod-tools`` to correct the
    syntax of the ``CifData`` node and remove/fix certain tags.

    If the ``--group-cif-structure`` option is specified the ``CifCleanWorkChain`` will attemp to parse the cleaned
    ``CifData`` node into a ``StructureData``.
    """
    # pylint: disable=too-many-locals
    from datetime import datetime
    from time import sleep

    from aiida.cmdline.utils import echo
    from aiida.engine import submit
    from aiida.orm import CifData, Dict, Group, ProcessNode, QueryBuilder, WorkChainNode
    from aiida.plugins import WorkflowFactory

    now = datetime.utcnow().isoformat

    cif_filter_parameters = {
        'fix-syntax-errors': True,
        'use-c-parser': True,
        'use-datablocks-without-coordinates': True,
    }

    cif_select_parameters = {
        'canonicalize-tag-names': True,
        'dont-treat-dots-as-underscores': True,
        'invert': True,
        'tags': '_publ_author_name,_citation_journal_abbrev',
        'use-c-parser': True,
    }

    node_cif_filter_parameters = QueryBuilder().append(Dict, filters={
        'attributes': {
            '==': cif_filter_parameters
        }
    }).first(flat=True) or Dict(cif_filter_parameters)

    node_cif_select_parameters = QueryBuilder().append(Dict, filters={
        'attributes': {
            '==': cif_select_parameters
        }
    }).first(flat=True) or Dict(cif_select_parameters)

    options = {
        'resources': {
            'num_machines': 1,
        },
        'max_wallclock_seconds': 1800,
        'withmpi': False,
    }

    inputs = {
        'cif_filter': {
            'code': cif_filter,
            'parameters': node_cif_filter_parameters,
            'metadata': {
                'options': options
            }
        },
        'cif_select': {
            'code': cif_select,
            'parameters': node_cif_select_parameters,
            'metadata': {
                'options': options
            }
        },
        'group_cif': group_cif_clean,
        'group_structure': group_cif_structure,
    }

    while True:

        # Check for excepted or killed processes indicating something might have gone wrong
        filters = {'attributes.process_state': {'or': [{'==': 'excepted'}, {'==': 'killed'}]}}
        query = QueryBuilder().append(ProcessNode, filters=filters)
        if query.count() > 0:
            echo.echo_critical(f'found {query.count()} excepted or killed processes, exiting.')

        # Count the current number of active processes
        filters = {'attributes.process_state': {'or': [{'==': 'waiting'}, {'==': 'running'}, {'==': 'created'}]}}
        query = QueryBuilder().append(WorkChainNode, filters=filters)
        current = query.count()
        max_entries = concurrent - current

        if current >= concurrent:
            echo.echo_report(f'{now()} | currently {current} running workchains, nothing to submit.')
            sleep(interval)
            continue

        # Get CifData nodes that already have an associated workchain node in the ``group_cif_workchain`` group.
        query = QueryBuilder()
        query.append(WorkChainNode, tag='workchain')
        query.append(Group, filters={'id': {'==': group_cif_workchain.pk}}, with_node='workchain')
        query.append(CifData, with_outgoing='workchain', tag='data', project=['id'])
        submitted_nodes = set(query.all(flat=True))

        if submitted_nodes:
            filters = {'id': {'!in': submitted_nodes}}
        else:
            filters = {}

        # Get CifData nodes that should actually be submitted according to the input filters
        query = QueryBuilder()
        query.append(Group, filters={'id': {'==': group_cif_data.pk}}, tag='group')
        query.append(CifData, with_group='group', filters=filters)
        query.limit(int(max_entries))

        for cif in query.all(flat=True):
            workchain = submit(WorkflowFactory('codtools.cif_clean'), cif=cif, **inputs)
            group_cif_workchain.add_nodes([workchain])
            echo.echo_report(f'{now()} | submitted CifData<{cif.uuid}>')

        echo.echo_report(f'{now()} | sleeping {interval} seconds.')
        sleep(interval)
