"""Take an organization pk and produce a graph of its BuildingSnapshot
View.
"""

from __future__ import unicode_literals

from django.db import models, migrations
from django.core.management.base import BaseCommand
from seed.lib.superperms.orgs.models import Organization
from django.apps import apps
import pdb
import copy
import collections
import os
import datetime
#import networkx as nx
#import matplotlib.pyplot as plt
#import pygraphviz
import logging
import itertools
from IPython import embed
#from networkx.drawing.nx_agraph import graphviz_layout
import seed.bluesky.models
import numpy as np
from scipy.sparse import dok_matrix
from scipy.sparse.csgraph import connected_components
from _localtools import projection_onto_index
from _localtools import get_static_building_snapshot_tree_file
from _localtools import read_building_snapshot_tree_structure
from _localtools import get_core_organizations
from _localtools import get_node_sinks

logging.basicConfig(level=logging.DEBUG)

def is_merge(node):
    return node.import_file_id is None

def check_import(node):
    return node.import_file_id is None or (is_tax_import(node) or is_pm_import(node))

def is_tax_import(node):
    return node.import_file_id is not None and node.tax_lot_id # and node.source_type in [0,2]

def is_pm_import(node):
    return node.import_file_id is not None and node.pm_property_id

def load_cycle(org, node):
    time = node.modified
    cycle = seed.bluesky.models.Cycle.objects.filter(organization=org, start__lt=time, end__gt=time).first()
    return cycle

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--org', dest='organization', default=False, type=int)
        return

    def handle(self, *args, **options):
        """Do something."""

        tree_file = get_static_building_snapshot_tree_file()
        m2m = read_building_snapshot_tree_structure(tree_file)

        all_nodes = set(map(projection_onto_index(0), m2m)).union(set(map(projection_onto_index(1), m2m)))
        child_dictionary = collections.defaultdict(lambda : set())
        parent_dictionary = collections.defaultdict(lambda : set())

        adj_dim = max(all_nodes) + 1
        adj_matrix = dok_matrix((adj_dim, adj_dim), dtype=np.bool)

        for (from_node, to_node) in m2m:
            adj_matrix[from_node, to_node] = 1
            child_dictionary[from_node].add(to_node)
            parent_dictionary[to_node].add(from_node)

        # Core data struct, possible refactor point.
        all_nodes, child_dictionary, parent_dictionary, adj_matrix

        # We don't care about the total number because
        _, labelarray = connected_components(adj_matrix)

        counts = collections.Counter()
        for label in labelarray: counts[label] += 1


        if 'organization' in options:
            core_organization = [options['organization']]
        else:
            core_organization = get_core_organizations()

        for org_id in core_organization:
            # Writing loop over organizations

            org = Organization.objects.filter(pk=org_id).first()
            logging.info("Processing organization {}".format(org))

            assert org, "Should get something back here."

            org_canonical_buildings = seed.models.CanonicalBuilding.objects.filter(canonical_snapshot__super_organization=org_id, active=True).all()
            org_canonical_snapshots = [cb.canonical_snapshot for cb in org_canonical_buildings]

            last_date = max([cs.modified for cs in org_canonical_snapshots])
            create_bluesky_cycles_for_org(org, last_date)

            tree_sizes = [counts[labelarray[bs.id]] for bs in org_canonical_snapshots]

            ## For each of those trees find the tip
            ## For each of those trees find the import records
            ## For each of those trees find the cycles associated with it
            print len(map(lambda x: x.id, org_canonical_snapshots))
            print len(set(map(lambda x: x.id, org_canonical_snapshots)))

            for ndx, bs in enumerate(org_canonical_snapshots):
                print "Processing Building {}/{}".format(ndx+1, len(org_canonical_snapshots))
                bs_label = labelarray[bs.id]
                # print "Label is {}".format(bs_label)
                import_nodes, leaf_nodes, other_nodes  = get_node_sinks(bs_label, labelarray, parent_dictionary, child_dictionary)

                # Load all those building snapshots
                tree_nodes = itertools.chain(import_nodes, leaf_nodes, other_nodes)
                building_dict = {bs.id: bs for bs in seed.models.BuildingSnapshot.objects.filter(pk__in=tree_nodes).all()}
                missing_buildings = [node for node in itertools.chain(import_nodes, leaf_nodes, other_nodes) if node not in building_dict]

                import_buildingsnapshots = [building_dict[bs_id] for bs_id in import_nodes]
                leaf_buildingsnapshots = [building_dict[bs_id] for bs_id in leaf_nodes]
                other_buildingsnapshots = [building_dict[bs_id] for bs_id in other_nodes]

                print "Creating snapshot for {}".format(leaf_buildingsnapshots[0])

                pdb.set_trace()
                create_associated_bluesky_taxlots_properties(org, import_buildingsnapshots, leaf_buildingsnapshots, other_buildingsnapshots, child_dictionary, parent_dictionary, adj_matrix)
        return


def create_associated_bluesky_taxlots_properties(org, import_buildingsnapshots, leaf_buildingsnapshots, other_buildingsnapshots, child_dictionary, parent_dictionary, adj_matrix):
    """Take tree structure describing a single Property/TaxLot over time and create the entities."""
    # logging.info("Creating a new entity thing-a-majig!")

    #print set([x.import_file for x in import_buildingsnapshots])

    tax_lot_created = 0
    property_created = 0
    tax_lot_view_created = 0
    property_view_created = 0
    tax_lot_state_created = 0
    property_state_created = 0
    m2m_created =  0

    logging.info("Creating Property/TaxLot from {} nodes".format( sum(map(len, (leaf_buildingsnapshots, other_buildingsnapshots, import_buildingsnapshots)))))

    cycle_map = {cycle.start.year: cycle for cycle in seed.bluesky.models.Cycle.objects.filter(organization=org).all()}

    all_nodes = list(itertools.chain(import_buildingsnapshots, leaf_buildingsnapshots, other_buildingsnapshots))
    all_nodes.sort(key = lambda rec: rec.created)

    tax_lot = None
    property = None

    tax_lot_views = {}
    property_views = {}


    merged_type = {}

    for node in all_nodes:
        assert check_import(node)

        if is_tax_import(node):
            merged_type[node.id] = "TAX"

            if tax_lot is None:
                #print "Creating tax lot"
                tax_lot = seed.bluesky.models.TaxLot(organization=org)
                tax_lot.save()
                tax_lot_created += 1
            new_state = seed.bluesky.models.TaxLotState(confidence = node.confidence,
                                                        jurisdiction_taxlot_identifier = node.tax_lot_id,
                                                        block_number = node.block_number,
                                                        district = node.district,
                                                        address = node.address_line_1,
                                                        city = node.city,
                                                        state = node.state_province,
                                                        postal_code = node.postal_code,
                                                        number_properties = node.building_count,
                                                        extra_data = copy.deepcopy(node.extra_data))
            new_state.save()
            tax_lot_state_created += 1
            cycle = load_cycle(org, node)

            if cycle.id in tax_lot_views:
                tax_lot_views[cycle.id].state = new_state
                tax_lot_views[cycle.id].save()
            else:
                tax_lot_views[cycle.id] = seed.bluesky.models.TaxLotView(taxlot=tax_lot, cycle=cycle, state = new_state)
                tax_lot_views[cycle.id].save()
                tax_lot_view_created += 1
        elif is_pm_import(node):
            merged_type[node.id] = "PM"
            if property is None:
                print "Creating Property"
                property = seed.bluesky.models.Property(organization=org)
                property.save()
                property_created += 1

            #print "Creating Property State"
            new_state = seed.bluesky.models.PropertyState(confidence = node.confidence,
                                                          jurisdiction_property_identifier = None,
                                                          lot_number = node.lot_number,
                                                          property_name = node.property_name,
                                                          address_line_1 = node.address_line_1,
                                                          address_line_2 = node.address_line_2,
                                                          city = node.city,
                                                          state = node.state_province,
                                                          postal_code = node.postal_code,
                                                          building_count = node.building_count,
                                                          property_notes = node.property_notes,
                                                          use_description = node.use_description,
                                                          gross_floor_area = node.gross_floor_area,
                                                          year_built = node.year_built,
                                                          recent_sale_date = node.recent_sale_date,
                                                          conditioned_floor_area = node.conditioned_floor_area,
                                                          occupied_floor_area = node.occupied_floor_area,
                                                          owner = node.owner,
                                                          owner_email = node.owner_email,
                                                          owner_telephone = node.owner_telephone,
                                                          owner_address = node.owner_address,
                                                          owner_city_state = node.owner_city_state,
                                                          owner_postal_code = node.owner_postal_code,
                                                          building_portfolio_manager_identifier = node.pm_property_id,
                                                          building_home_energy_score_identifier = None,
                                                          energy_score = node.energy_score,
                                                          site_eui = node.site_eui,
                                                          generation_date = node.generation_date,
                                                          release_date = node.release_date,
                                                          site_eui_weather_normalized = node.site_eui_weather_normalized,
                                                          source_eui = node.source_eui,
                                                          energy_alerts = node.energy_alerts,
                                                          space_alerts = node.space_alerts,
                                                          building_certification = node.building_certification,
                                                          extra_data = copy.deepcopy(node.extra_data))
            new_state.save()
            property_state_created += 1
            cycle = load_cycle(org, node)

            if cycle.id in property_views:
                #print "Updating ProperyView"
                property_views[cycle.id].state = new_state
                property_views[cycle.id].save()
            else:
                #print "Creating ProperyView"
                property_views[cycle.id] = seed.bluesky.models.PropertyView(property=property, cycle=cycle, state = new_state)
                property_views[cycle.id].save()
                property_view_created += 1

        elif is_merge(node):
            # A merge in the old-world represents an m2m in the previous world.
            # IF the merge joins a tax lot and a parent record.

            node_parents = parent_dictionary[node.id]
            err_msg = "{} is a bad number of parents".format(len(node_parents))

            try:
                assert len(node_parents) == 2, err_msg
            except:
                pdb.set_trace()

            types = [merged_type[x] for x in node_parents]
            if len(set(types)) == 2:
                cycle = load_cycle(org, node)
                property_view_to_merge = property_views[cycle.id]
                tl_view_to_merge = tax_lot_views[cycle.id]

                #print "Creating M2M!"
                tlp = seed.bluesky.models.TaxLotProperty(property_view = property_view_to_merge,
                                                         taxlot_view = tl_view_to_merge,
                                                         cycle = cycle)
                m2m_created += 1
                tlp.save()
            elif "TAX" in types:
                merged_type[node.id] = "TAX"

                if tax_lot is None:
                    #print "Creating tax lot"
                    tax_lot = seed.bluesky.models.TaxLot(organization=org)
                    tax_lot.save()
                    tax_lot_created += 1

                #print "Creating tax lot state"
                new_state = seed.bluesky.models.TaxLotState.objects.create(confidence = node.confidence,
                                                                           jurisdiction_taxlot_identifier = node.tax_lot_id,
                                                                           block_number = node.block_number,
                                                                           district = node.district,
                                                                           address = node.address_line_1,
                                                                           city = node.city,
                                                                           state = node.state_province,
                                                                           postal_code = node.postal_code,
                                                                           number_properties = node.building_count,
                                                                           extra_data = copy.deepcopy(node.extra_data))
                new_state.save()
                tax_lot_state_created += 1
                cycle = load_cycle(org, node)

                if cycle.id in tax_lot_views:
                    #print "Updating Tax Lot View"
                    tax_lot_views[cycle.id].state = new_state
                    tax_lot_views[cycle.id].save()
                else:
                    #print "Creating Tax Lot View"
                    tax_lot_views[cycle.id] = seed.bluesky.models.TaxLotView(taxlot=taxlot, cycle=cycle, state = new_state)
                    tax_lot_views[cycle.id].save()
                    tax_lot_view_created += 1
            elif "PM" in types:
                merged_type[node.id] = "PM"
                if property is None:
                    #print "Creating Property"
                    property = seed.bluesky.models.Property(organization=org)
                    property.save()
                    property_created += 1

                #print "Creating property state"
                new_state = seed.bluesky.models.PropertyState(confidence = node.confidence,
                                                                             jurisdiction_property_identifier = None,
                                                              lot_number = node.lot_number,
                                                              property_name = node.property_name,
                                                              address_line_1 = node.address_line_1,
                                                              address_line_2 = node.address_line_2,
                                                              city = node.city,
                                                              state = node.state_province,
                                                              postal_code = node.postal_code,
                                                              building_count = node.building_count,
                                                              property_notes = node.property_notes,
                                                              use_description = node.use_description,
                                                              gross_floor_area = node.gross_floor_area,
                                                              year_built = node.year_built,
                                                              recent_sale_date = node.recent_sale_date,
                                                              conditioned_floor_area = node.conditioned_floor_area,
                                                              occupied_floor_area = node.occupied_floor_area,
                                                              owner = node.owner,
                                                              owner_email = node.owner_email,
                                                              owner_telephone = node.owner_telephone,
                                                              owner_address = node.owner_address,
                                                              owner_city_state = node.owner_city_state,
                                                              owner_postal_code = node.owner_postal_code,
                                                              building_portfolio_manager_identifier = pm_property_id,
                                                              building_home_energy_saver_identifier = None,
                                                              energy_score = node.energy_score,
                                                              site_eui = node.site_eui,
                                                              generation_date = node.generation_date,
                                                              release_date = node.release_date,
                                                              site_eui_weather_normalized = note.site_eui_weather_normalized,
                                                              source_eui = node.source_eui,
                                                              energy_alerts = node.energy_alerts,
                                                              space_alerts = node.space_alerts,
                                                              building_certification = node.building_certification,
                                                              extra_data = copy.deepcopy(extra_data))
                new_state.save()
                property_state_created += 1


                cycle = load_cycle(org, node)

                if cycle.id in property_views:
                    #print "Updating Property View"
                    property_views[cycle.id].state = new_state
                    property_views[cycle.id].save()
                else:
                    #print "Creating Property View"
                    property_views[cycle.id] = seed.bluesky.models.PropertyView(property = property, cycle=cycle, state = new_state)
                    property_views[cycle.id].save()
                    property_view_created += 1

    logging.info("{} Tax Lot, {} Property, {} TaxLotView, {} PropertyView, {} TaxLotState, {} PropertyState, {} m2m created.".format(tax_lot_created,
                                                                                                                                      property_created,
                                                                                                                                      tax_lot_view_created,
                                                                                                                                      property_view_created ,
                                                                                                                                      tax_lot_state_created ,
                                                                                                                                      property_state_created,
                                                                                                                                      m2m_created))

    return


def create_bluesky_cycles_for_org(org, last_date):

    for year in xrange(2000, last_date.year + 1):
        start_cycle_date = datetime.datetime(year, 1, 1, 0, 0)
        end_cycle_date = datetime.datetime(year+1, 1, 1, 0, 0) - datetime.timedelta(seconds = 1)
        name = "{} Calendar Year".format(year)

        cycle, created = seed.bluesky.models.Cycle.objects.get_or_create(organization =org,
                                                                         name = name,
                                                                         start = start_cycle_date,
                                                                         end = end_cycle_date)
    return