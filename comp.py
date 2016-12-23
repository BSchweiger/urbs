import glob
import math
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import matplotlib.ticker as tkr
import os
import pandas as pd
import urbs
import sys

# INIT



def get_most_recent_entry(search_dir):
    """ Return most recently modified entry from given directory.
    
    Args:
        search_dir: an absolute or relative path to a directory
        
    Returns:
        The file/folder in search_dir that has the most recent 'modified'
        datetime.
    """
    entries = glob.glob(os.path.join(search_dir, "*"))
    entries.sort(key=lambda x: os.path.getmtime(x))
    return entries[-1]

def glob_result_files(folder_name):
    """ Glob result spreadsheets from specified folder. 
    
    Args:
        folder_name: an absolute or relative path to a directory
        
    Returns:
        list of filenames that match the pattern 'scenario_*.xlsx'
    """
    glob_pattern = os.path.join(folder_name, 's*.xlsx')
    result_files = sorted(glob.glob(glob_pattern))
    return result_files
    
def deduplicate_legend(handles, labels):
    """ Remove double entries from figure legend.
    
    Args:
        handles: list of legend entry handles
        labels: list of legend entry labels
        
    Returns:
        (handles, labels) tuple of lists with duplicate labels removed
    """
    new_handles = []
    new_labels = []
    for hdl, lbl in zip(handles, labels):
        if not lbl in new_labels:
            new_handles.append(hdl)
            new_labels.append(lbl)
    # also, sort both lists accordingly            
    new_labels, new_handles = (list(t) for t in zip(*sorted(zip(new_labels, new_handles))))
    return (new_handles, new_labels)
    
def group_hbar_plots(ax, group_size, inner_sep=None):
    """
    Args:
        ax: matplotlib axis
        group_size (int): how many bars to group together
        inner_sep (float): vertical spacing within group (optional)
    """
    handles, labels = ax.get_legend_handles_labels()
    bar_height = handles[0][0].get_height()  # assumption: all bars identical 
    
    if not inner_sep:
        inner_sep = 0.5 * (1 - bar_height)
    
    for column, handle in enumerate(handles):
        for row, patch in enumerate(handle.patches):
            group_number, row_within_group = divmod(row, group_size)
            
            group_offset = (group_number * group_size
                            + 0.5 * (group_size - 1) * (1 - inner_sep)
                            - 0.5 * (group_size * bar_height))
            
            patch.set_y(row_within_group * (bar_height + inner_sep)
+ group_offset)


def compare_scenarios(result_files, output_filename):
    """ Create report sheet and plots for given report spreadsheets.
    
    Args:
        result_files: a list of spreadsheet filenames generated by urbs.report
        output_filename: a spreadsheet filename that the comparison is to be 
                         written to
                         
     Returns:
        Nothing
    
    To do: 
        Don't use report spreadsheets, instead load pickled problem 
        instances. This would make this function less fragile and dependent
        on the output format of urbs.report().
    """
        
    # derive list of scenario names for column labels/figure captions
    scenario_names = [os.path.basename(rf) # drop folder names, keep filename
                      .replace('_', ' ') # replace _ with spaces
                      .replace('.xlsx', '') # drop file extension
                      .replace('scenario ', '') # drop 'scenario ' prefix
                      for rf in result_files]    
    
    # find base scenario and put at first position
    try:
        base_scenario = scenario_names.index('base')
        result_files.insert(0, result_files.pop(base_scenario))
        scenario_names.insert(0, scenario_names.pop(base_scenario))
    except ValueError:
        pass # do nothing if no base scenario is found
    
    costs = []  # total costs by type and scenario
    esums = []  # sum of energy produced by scenario
    caps = []
    
    # READ
    
    for rf in result_files:
        with pd.ExcelFile(rf) as xls:
            cost = xls.parse('Costs',index_col=[0])
            esum = xls.parse('Commodity sums')
            cap = xls.parse('Process caps', index_col=[0,1])
    
            # repair broken MultiIndex in the first column
            esum.reset_index(inplace=True)
            esum.fillna(method='ffill', inplace=True)
            esum.set_index(['index', 'pro'], inplace=True)
            
            cap = cap['Total'].loc['Campus']
            
            costs.append(cost)
            esums.append(esum)
            caps.append(cap)
    
    # merge everything into one DataFrame each
    costs = pd.concat(costs, axis=1, keys=scenario_names)
    esums = pd.concat(esums, axis=1, keys=scenario_names)
    caps = pd.concat(caps, axis=1, keys=scenario_names)
    
    # ANALYSE
    
    # drop redundant 'costs' column label
    # make index name nicer for plot
    # sort/transpose frame
    # only keep cost types with non-zero value around
    costs.columns = costs.columns.droplevel(1)
    costs.index.name = 'Cost type'
    costs = costs.sort_index().transpose()
    spent = costs.loc[:, costs.sum() > 0]
    earnt = costs.loc[:, costs.sum() < 0]
    
    # sum up created energy over all locations, but keeping scenarios (level=0)
    created  =   esums.loc['Created'].rename(columns=lambda x:x.replace('.Campus','')).T
    consumed = - esums.loc['Consumed'].rename(columns=lambda x:x.replace('.Campus','')).T.drop('Demand', axis=1)
    
    created = created.loc[:, created.sum() > 0.1] / 1e3
    consumed = consumed.loc[:, consumed.sum() < - 0.1] / 1e3
    
    created = created.sort_index(ascending=[False, True])
    consumed = consumed.sort_index(ascending=[False, True])    
    
    sto_sums = esums.loc[('Storage', 'Retrieved')].sort_index()
    #sto_sums = sto_sums.unstack()
    sto_sums = sto_sums.rename(index=lambda x:x.replace('.Campus',''))
    sto_sums = sto_sums / 1e3

    # hack to make this data conform to the same structure as the DataFrames
    # created and consumed:
    #  index: MultiIndex of tuples (scenario, commodity)
    #  columns: process (technology)
    #
    # right now, sto_sums does not contain the technology, so there is only
    # one column. But for presentational (legend) reasons, splitting the 
    # single column 'Storage retreived' into two columns, one for each
    # commodity, allows for separate styling (i.e. legend entries).
    sto_sums = sto_sums = pd.concat([sto_sums, sto_sums], axis=1)
    sto_sums.columns = ['Battery', 'Reservoir']
    sto_sums = sto_sums.sort_index()
    sto_sums.loc[(slice(None), 'Elec'), 'Reservoir'] = 0
    sto_sums.loc[(slice(None), 'Heat'), 'Battery'] = 0
    sto_sums = sto_sums.sort_index(ascending=[False, True])
    
    # remove CO2 from bar charts
    for df in [created, consumed, sto_sums]:
        df.drop('CO2', level=1, inplace=True)
    
    # PLOT
    
    fig = plt.figure(figsize=(24, 10))
    gs = gridspec.GridSpec(1, 3, width_ratios=[5, 8, 2], wspace=0.03)
    
    ax0 = plt.subplot(gs[0])
    spent_colors = [urbs.to_color(cost_type) for cost_type in spent.columns]
    bp0 = spent.plot(ax=ax0, kind='barh', color=spent_colors, stacked=True,
                     linewidth=0)
    if not earnt.empty:
        earnt_colors = [urbs.to_color(cost_type) for cost_type in earnt.columns]
        bp0a = earnt.plot(ax=ax0, kind='barh', color=earnt_colors, stacked=True,
                          linewidth=0)
    
    ax1 = plt.subplot(gs[1])
    created_colors = [urbs.to_color(commodity) for commodity in created.columns]
    bp1 = created.plot(ax=ax1, kind='barh', stacked=True, color=created_colors,
                       linewidth=0, width=.5)
    if not consumed.empty:
        consumed_colors = [urbs.to_color(commodity) for commodity in consumed.columns]
        bp1a = consumed.plot(ax=ax1, kind='barh', stacked=True, color=consumed_colors,
                             linewidth=0, width=.5)
    
    ax2 = plt.subplot(gs[2])
    stored_colors = [urbs.to_color(commodity) for commodity in sto_sums.columns]
    bp2 = sto_sums.plot(ax=ax2, kind='barh', stacked=True, color=stored_colors,
                        linewidth=0)
    
    # remove scenario names from other bar plots
    for ax in [ax1, ax2]:
        ax.set_yticklabels('')
        group_hbar_plots(ax, 3)
    
    # set limits and ticks for both axes
    for ax in [ax0, ax1, ax2]:
        plt.setp(list(ax.spines.values()), color=urbs.to_color('Grid'))
        ax.yaxis.grid(False)
        ax.xaxis.grid(True, 'major', color=urbs.to_color('Grid'), linestyle='-')
        ax.xaxis.set_ticks_position('none')
        ax.yaxis.set_ticks_position('none')
        
        # group 1,000,000 with commas
        xmin, xmax = ax.get_xlim()
        if xmax > 90 or xmin < -90:
            group_thousands_and_skip_first = tkr.FuncFormatter(
                lambda x, pos: '' if pos == 0 else '{:0,d}'.format(int(x)))
            ax.xaxis.set_major_formatter(group_thousands_and_skip_first )
        else:
            skip_lowest = tkr.FuncFormatter(
                lambda x, pos: '' if pos == 0 else x)
            ax.xaxis.set_major_formatter(skip_lowest)
    
        # legend
        # set style arguments
        legend_style= {'frameon': False, 
                       'loc': 'lower center',
                       'ncol': 4, 
                       'bbox_to_anchor': (0.5, .99) }   
        # get handels and labels, remove duplicate labels
        handles, labels = deduplicate_legend(*ax.get_legend_handles_labels())        
        # set legend to use those
        lg = ax.legend(handles, labels, **legend_style)
        # finally, remove lines from patches
        plt.setp(lg.get_patches(), 
                 edgecolor=urbs.to_color('Decoration'),
                 linewidth=0)

    ax0.set_xlabel('Total costs (Mio.€/a)')
    ax1.set_xlabel('Total energy produced (GWh)')
    ax2.set_xlabel('Retrieved energy (GWh)')
    
    for ext in ['png', 'pdf']:
        fig.savefig('{}.{}'.format(output_filename, ext),
                    bbox_inches='tight')
    
    # REPORT
    with pd.ExcelWriter('{}.{}'.format(output_filename, 'xlsx')) as writer:
        costs.to_excel(writer, 'Costs')
        esums.to_excel(writer, 'Energy sums')
        caps.to_excel(writer, 'Process caps')
        
if __name__ == '__main__':
    
    # add or change plot colors
    my_colors = {
        'Battery': (100, 160, 200),
        'Demand': (0, 0, 0),
        'Gas Plant': (218, 215, 203),
        'Heat changer': (218, 215, 203),
        'Gas boiler': (218, 215, 203),
        'Absorption chiller': (0, 101, 189),
        'Compression chiller': (100, 160, 200),
        'Import(Heat)': (180, 50, 15),
        'Feed-in': (62, 173, 0),
        'Heating rod': (180, 50, 15),
        'Heatpump': (227, 114, 34),
        'P2H': (180, 50, 15),
        'PVS30': (62, 173, 0),
        'Purchase': (0, 119, 138),
        'Solarthermal': (255, 220, 0),
        'Storage': (100, 160, 200),
        'Stock': (255, 128, 0),
        'Reservoir': (196, 7, 27),
        'Fixed': (128, 128, 128),
        'Fuel': (218, 215, 203),
        'Invest': (0, 101, 189), 
        'Revenue': (62, 173, 0),
        'Purchase': (0, 51, 89),
        'Variable': (128, 153, 172),
    }
    for country, color in my_colors.items():
        urbs.COLORS[country] = color
    
    directories = sys.argv[1:]
    if not directories:
        # get the directory of the supposedly last run
        # and retrieve (glob) a list of all result spreadsheets from there
        directories = [get_most_recent_entry('result')]
    
    for directory in directories:
        result_files = glob_result_files(directory)
        
        # specify comparison result filename 
        # and run the comparison function
        comp_filename = os.path.join(directory, 'comparison')
compare_scenarios(list(reversed(result_files)), comp_filename)