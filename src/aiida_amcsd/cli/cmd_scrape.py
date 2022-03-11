# -*- coding: utf-8 -*-
"""CLI command to scrape the AMCSD to download structures in CIF format."""
from aiida.cmdline.params.types import GroupParamType
import click

from .cli import cli


@cli.command('scrape')
@click.option(
    '-F',
    '--group-cif-file',
    type=GroupParamType(create_if_not_exist=True),
    required=True,
    help='Group to store the scraped CIF files in as ``SinglefileData`` nodes.'
)
@click.option(
    '--cache',
    type=click.Path(dir_okay=False, writable=True),
    default='amcsd.cache',
    help='Filepath to the cache.',
    show_default=True
)
@click.option('-M', '--max-number', type=click.INT, required=False, help='Limit number of minerals to scrape.')
@click.option('-n', '--dry-run', is_flag=True, help='Perform a dry-run and do not store any provenance.')
def cmd_scrape(group_cif_file, cache, max_number, dry_run):
    """Scrape the AMCSD to download structures in CIF format.

    The command uses ``beautifulsoup`` to parse the content of ``http://rruff.geo.arizona.eduAMS/all_minerals.php`` for
    a list of all available minerals. Then for each mineral, its corresponding page is scraped for links that allow to
    download its structure as a CIF which is then wrapped in a ``SinglefileData`` node and added the ``Group``
    provided by the ``-F/--group-cif-file`` option.

    The requests are cached which is written to a file on disk provided by the ``--cache`` option.
    """
    # pylint: disable=too-many-locals
    import io
    import re

    from aiida.cmdline.utils import echo
    from aiida.common.files import md5_from_filelike
    from aiida.orm import SinglefileData
    import bs4
    import requests
    import requests_cache

    requests_cache.install_cache(cache)

    base_url = 'http://rruff.geo.arizona.edu'
    response = requests.get(f'{base_url}/AMS/all_minerals.php')
    soup_all = bs4.BeautifulSoup(response.text, 'html.parser')
    minerals = []
    cif_files = []

    for link in soup_all.find_all('a'):

        href = link.get('href')

        if href.startswith('/AMS/minerals'):
            minerals.append(href)

    echo.echo_report(f'found links for {len(minerals)} minerals.')

    with click.progressbar(minerals[:max_number], width=0, bar_template='%(label)-50s [%(bar)s] %(info)s') as links:
        for link_mineral in links:

            mineral_name = link_mineral.split('/')[-1]
            links.label = click.style('Downloading: ', fg='blue', bold=True) + mineral_name

            try:
                response_mineral = requests.get(f'{base_url}{link_mineral}')
            except requests.HTTPError as exc:
                echo.echo_error(f'retrieving link `{link_mineral}` failed: {exc}')
                continue

            soup_mineral = bs4.BeautifulSoup(response_mineral.text, 'html.parser')

            for anchor in soup_mineral.find_all('a'):

                if anchor.get_text() != 'Download CIF data':
                    continue

                link_cif = f"{base_url}{anchor.get('href')}"

                try:
                    response_cif = requests.get(link_cif)
                except requests.HTTPError as exc:
                    echo.echo_error(f'retrieving CIF link `{link_cif}` failed: {exc}')
                    continue

                byte_stream = io.BytesIO(response_cif.text.encode('utf-8'))
                md5 = md5_from_filelike(byte_stream)
                byte_stream.seek(0)

                matches = re.match(r'^.*?id=([0-9]+)\.cif.*$', link_cif)
                cif_file = SinglefileData(file=byte_stream, filename=f'{mineral_name}.cif')
                cif_file.set_attribute('source', {'id': matches.group(1), 'name': mineral_name, 'url': link_cif})
                cif_file.set_attribute('md5', md5)

                cif_files.append(cif_file)
                break

            else:
                echo.echo_error(f'failed to download a CIF for {mineral_name}')

        echo.echo_success('scraping completed, adding to group.')
        if not dry_run:
            group_cif_file.add_nodes([cif_file.store() for cif_file in cif_files])

    echo.echo_success(f'stored {len(cif_files)} CIF files in `{group_cif_file.label}`.')
