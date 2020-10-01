import csv

import click
from flask import current_app
from flask.cli import with_appcontext

from parasolr.solr.client import SolrClient


@click.command()
@click.argument('csvpath')
@with_appcontext
def index(csvpath):
    print('Indexing %s' % csvpath)
    solr = SolrClient(current_app.config['SOLR_URL'],
                      current_app.config['SOLR_CORE'])

    # clear the index in case any records have been removed or merged
    solr.update.delete_by_query('*:*')

    with open(csvpath) as csvfile:
        csvreader = csv.DictReader(csvfile)
        rows = list(csvreader)
        # check that pgp ids are unique
        pgpids = [row['PGPID'] for row in rows]
        if len(pgpids) != len(set(pgpids)):
            print('Warning: PGPIDs are not unique!')

        # index pgp data into Solr
        solr.update.index([{
            # use PGPID as Solr identifier
            'id': row['PGPID'],
            'description_txt': row['Description'],
            'type_s': row['Type'],
            'library_s': row['Library'],
            'shelfmark_s': row['Shelfmark - Current'],
            'shelfmark_txt': row['Shelfmark - Current'],
            'tags_txt': [tag.strip() for tag in row['Tags'].split('#')],
            'tags_ss': [tag.strip() for tag in row['Tags'].split('#')],
            'link_s': row['Link to image'],
            'editors_txt': row['Editor(s)'],
            'translators_txt': row['Translator (optional)']
        } for row in rows], commitWithin=100)

        print(f'Indexed {len(rows):,} records')

#MR: Library, shelfmark, description, tags, editor(s), translator — tentative list, let’s discuss.
