

import pandas as pd
import panel as pn
import hvplot.pandas
import plotly.graph_objects as go
pn.extension('tabulator', 'plotly')
import geopandas as gpd
import folium
from folium import plugins

# 1. Load data for multiple watersheds
watersheds_data = {
    'Yackanookany': r"C:\Users\ishret\Desktop\AnnAGNPS_papers\Yackanookany\ET\merged_ET_data.csv",
    'Pearl River at Burnside': r"C:\Users\ishret\Desktop\AnnAGNPS_papers\Pearl_River_at_Burnside\ET\merged_ET_data.csv",
}

watersheds_geometry = {
    'Yackanookany': r"C:\Users\ishret\Desktop\AnnAGNPS_papers\Yackanookany\yac_AIMS_no_ET\GIS\cells_geometry.gpkg",
    'Pearl River at Burnside': r"C:\Users\ishret\Desktop\AnnAGNPS_papers\Pearl_River_at_Burnside\Burnside_AIMS_NO_ET_NOAH\GIS\pearl_river_cell.gpkg",
}


# Add discharge data paths
watersheds_discharge = {
    'Yackanookany': r"C:\Users\ishret\Desktop\AnnAGNPS_papers\Yackanookany\Runoff\yac_cms_runoff_all.csv",
    'Pearl River at Burnside': r"C:\Users\ishret\Desktop\AnnAGNPS_papers\Pearl_River_at_Burnside\downstream_runoff\downstream_runoff_all_cms.csv",
}


# Load all watershed data into a dictionary
watershed_dfs = {}
for watershed_name, file_path in watersheds_data.items():
    try:
        df = pd.read_csv(file_path)
        df = df.rename(columns={'Model_aclculated_ET': 'Model_calculated_ET'})
        df['Date'] = pd.to_datetime(df['Date'])
        df['year'] = df['Date'].dt.year
        watershed_dfs[watershed_name] = df
    except FileNotFoundError:
        print(f"Warning: File not found for {watershed_name}: {file_path}")

# Load discharge data
watershed_discharge_dfs = {}
for watershed_name, file_path in watersheds_discharge.items():
    try:
        df = pd.read_csv(file_path)
        # Adjust these column names based on your actual CSV structure
        df['Date'] = pd.to_datetime(df['Date'])  # or whatever your date column is named
        df['year'] = df['Date'].dt.year
        watershed_discharge_dfs[watershed_name] = df
        print(f"Loaded discharge data for {watershed_name}: {len(df)} records")
    except FileNotFoundError:
        print(f"Warning: Discharge file not found for {watershed_name}: {file_path}")
    except Exception as e:
        print(f"Warning: Error loading discharge data for {watershed_name}: {e}")
        
# Load watershed geometries (with pre-projection for speed)
watershed_geometries = {}
for watershed_name, geom_path in watersheds_geometry.items():
    try:
        gdf = gpd.read_file(geom_path)
        
        if gdf.crs and gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")
            
        watershed_geometries[watershed_name] = gdf
        print(f"Loaded {watershed_name}: {len(gdf)} features")
    except Exception as e:
        print(f"Warning: Could not load geometry for {watershed_name}: {e}")

# 2. Widgets
watershed_dropdown = pn.widgets.Select(
    name='Watershed',
    options=list(watershed_dfs.keys()),
    value=list(watershed_dfs.keys())[0] 
)

year_dropdown = pn.widgets.Select(
    name='Year',
    options=[],  
    value=None
)

# Update year options when watershed changes
@pn.depends(watershed_dropdown, watch=True)
def update_year_options(watershed):
    if watershed in watershed_dfs:
        years = sorted(watershed_dfs[watershed]['year'].unique().tolist())
        year_dropdown.options = years
        year_dropdown.value = int(years[0]) if years else None

# Initialize year options
update_year_options(watershed_dropdown.value)

# 3. Plot with interactive legend and month names - FIXED Y-AXIS RANGE
@pn.depends(watershed_dropdown, year_dropdown)
def et_plot(watershed, year):
    if watershed not in watershed_dfs or year is None:
        return pn.pane.Markdown("### No data available")
    
    df = watershed_dfs[watershed]
    df_year = (
        df[df['year'] == year]
        .sort_values('Date')
        .reset_index(drop=True)
    )

    if df_year.empty:
        return pn.pane.Markdown(f"### No data available for {watershed} in year {year}")

    # Add a month name column
    df_year['Month'] = df_year['Date'].dt.strftime('%b')
    
    # Plot all three ET sources
    y_cols = ['Model_calculated_ET', 'MODIS_ET', 'Noah_LSM_ET']

    # 🔹 FIX: Calculate appropriate y-axis range for ET data (small values)
    et_min = df_year[y_cols].min().min()
    et_max = df_year[y_cols].max().max()
    y_padding = (et_max - et_min) * 0.15  # 15% padding for better visibility
    y_min_limit = max(0, et_min - y_padding)
    y_max_limit = et_max + y_padding
    
    curve = df_year.hvplot(
        x='Date',
        y=y_cols,
        line_width=2,
        xlabel='Month',
        ylabel='ET (mm/day)',
        tools=['pan', 'xwheel_zoom', 'ywheel_zoom', 'box_zoom', 'reset', 'hover'],
        active_tools=['xwheel_zoom'],
        muted_alpha=0.2,
        xticks=12,
        grid=True,
        shared_axes=False  # 🔹 Prevent axis sharing with other plots
    )

    from bokeh.models.formatters import DatetimeTickFormatter
    
    formatter = DatetimeTickFormatter(
        days='%b',
        months='%b',
        years='%b'
    )

    return curve.opts(
        title="",
        show_title=False,
        legend_position='top',
        legend_cols=3,
        legend_opts={'title': '', 'click_policy': 'mute'},
        height=400,
        frame_height=350,
        width=800,
        frame_width=750,
        xformatter=formatter,
        ylim=(y_min_limit, y_max_limit)  # 🔹 Set ET-appropriate range in opts
    )

# Add a widget to select which field to color by
field_selector = pn.widgets.Select(
    name='Color by Field',
    options=['mgmt_field_id'],
    value='mgmt_field_id'
)
# 3b. Map with watershed cells
@pn.depends(watershed_dropdown, field_selector)
def watershed_map(watershed, selected_field):
    if watershed not in watershed_geometries:
        return pn.pane.Markdown("### Map not available for this watershed")
    
    gdf = watershed_geometries[watershed]
    
    if gdf.empty:
        return pn.pane.Markdown("### No geometry data available")
    
    if selected_field not in gdf.columns:
        return pn.pane.Markdown(f"### Field '{selected_field}' not found in data")
    
    bounds = gdf.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=10,
        tiles='OpenStreetMap'
    )
    
    unique_values = gdf[selected_field].unique()
    
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors
    
    colormap = cm.get_cmap('tab20', len(unique_values))
    
    value_colors = {}
    for i, value in enumerate(unique_values):
        rgba = colormap(i)
        hex_color = mcolors.rgb2hex(rgba)
        value_colors[value] = hex_color
    
    def style_function(feature):
        field_value = feature['properties'].get(selected_field)
        return {
            'fillColor': value_colors.get(field_value, '#88d8b0'),
            'color': '#2d5f4a',
            'weight': 0,
            'fillOpacity': 0.6
        }
    
    folium.GeoJson(
        gdf,
        name='Watershed Cells',
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=[selected_field],
            aliases=[f'{selected_field}:'],
            localize=True
        ),
        highlight_function=lambda x: {
            'fillColor': '#ffff00',
            'fillOpacity': 0.8,
            'weight': 3
        }
    ).add_to(m)
    
    legend_html = f'''
    <div style="position: fixed; 
                bottom: 50px; right: 50px; width: 200px; max-height: 300px; overflow-y: auto;
                background-color: white; z-index:9999; font-size:12px;
                border:2px solid grey; border-radius: 5px; padding: 10px">
    <p style="margin-top:0; font-weight: bold; font-size:14px;">{selected_field}</p>
    '''
    for value, color in value_colors.items():
        legend_html += f'<p style="margin: 3px 0;"><i style="background:{color}; width: 18px; height: 10px; display: inline-block; margin-right: 5px;"></i>{value}</p>'
    legend_html += '</div>'
    
    m.get_root().html.add_child(folium.Element(legend_html))
    
    folium.LayerControl().add_to(m)
    
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    
    return pn.pane.HTML(m._repr_html_(), height=500, width=800)

# 3c. Discharge comparison plot - FIXED Y-AXIS RANGE
@pn.depends(watershed_dropdown, year_dropdown)
def discharge_plot(watershed, year):
    if watershed not in watershed_discharge_dfs or year is None:
        return pn.pane.Markdown("### No discharge data available")
    
    df = watershed_discharge_dfs[watershed]
    df_year = (
        df[df['year'] == year]
        .sort_values('Date')
        .reset_index(drop=True)
    )

    if df_year.empty:
        return pn.pane.Markdown(f"### No discharge data available for {watershed} in year {year}")

    df_year['Month'] = df_year['Date'].dt.strftime('%b')
    
    # Adjust these column names based on your actual CSV
    # Assuming columns like: 'USGS_Discharge', 'Model_ET_Discharge', 'MODIS_ET_Discharge', 'Noah_LSM_ET_Discharge'
    y_cols = ['USGS_Runoff_cms', 'Runoff_No_ET_cms', 'Runoff_MODIS_ET_cms', 'Runoff_NOAH_ET_cms']
    
    # Filter to only columns that exist in the dataframe
    y_cols = [col for col in y_cols if col in df_year.columns]
    
    if not y_cols:
        return pn.pane.Markdown("### Discharge columns not found in data")

    # 🔹 FIX: Calculate appropriate y-axis range for discharge data (large values)
    discharge_min = df_year[y_cols].min().min()
    discharge_max = df_year[y_cols].max().max()
    y_padding = (discharge_max - discharge_min) * 0.15  # 15% padding for better visibility
    y_min_limit = max(0, discharge_min - y_padding)
    y_max_limit = discharge_max + y_padding
    
    curve = df_year.hvplot(
        x='Date',
        y=y_cols,
        line_width=2,
        xlabel='Month',
        ylabel='Discharge (m³/s)',
        tools=['pan', 'xwheel_zoom', 'ywheel_zoom', 'box_zoom', 'reset', 'hover'],
        active_tools=['xwheel_zoom'],
        muted_alpha=0.2,
        xticks=12,
        grid=True,
        shared_axes=False  # 🔹 Prevent axis sharing with other plots
    )

    from bokeh.models.formatters import DatetimeTickFormatter
    
    formatter = DatetimeTickFormatter(
        days='%b',
        months='%b',
        years='%b'
    )

    return curve.opts(
        title="",
        show_title=False,
        legend_position='top',
        legend_cols=4,
        legend_opts={'title': '', 'click_policy': 'mute'},
        height=400,
        frame_height=350,
        width=800,
        frame_width=750,
        xformatter=formatter,
        ylim=(y_min_limit, y_max_limit)  # 🔹 Set discharge-appropriate range in opts
    )

# Update field selector options when watershed changes
@pn.depends(watershed_dropdown, watch=True)
def update_field_options(watershed):
    if watershed in watershed_geometries:
        gdf = watershed_geometries[watershed]
        available_fields = [col for col in gdf.columns if col != 'geometry']
        field_selector.options = available_fields
        if 'mgmt_field_id' in available_fields:
            field_selector.value = 'mgmt_field_id'
        elif available_fields:
            field_selector.value = available_fields[0]

# Initialize field options
update_field_options(watershed_dropdown.value)

# 4. Table: first 20 rows for selected watershed and year
@pn.depends(watershed_dropdown, year_dropdown)
def et_table(watershed, year):
    if watershed not in watershed_dfs or year is None:
        return pn.pane.Markdown("No data available")
    
    df = watershed_dfs[watershed]
    df_year = (
        df[df['year'] == year]
        .sort_values('Date')
        .reset_index(drop=True)
    )
    
    df_display = df_year.copy()
    df_display['Date'] = df_display['Date'].dt.strftime('%Y-%m-%d')
    df_display = df_display.drop(columns=['year'])
    
    return pn.widgets.Tabulator(
        df_display.head(20),
        show_index=False
    )

# 5. Download buttons for ET and Discharge data
@pn.depends(watershed_dropdown, year_dropdown)
def download_et_button(watershed, year):
    """Download button for ET data"""
    if watershed not in watershed_dfs or year is None:
        return pn.pane.Markdown("*Select watershed and year*")
    
    df = watershed_dfs[watershed]
    df_full = (
        df[df['year'] == year]
        .sort_values('Date')
        .reset_index(drop=True)
    )
    
    if df_full.empty:
        return pn.pane.Markdown("*No ET data available*")
    
    df_download = df_full.copy()
    df_download['Date'] = df_download['Date'].dt.strftime('%Y-%m-%d')
    df_download = df_download.drop(columns=['year'])
    
    import io
    sio = io.StringIO()
    df_download.to_csv(sio, index=False)
    sio.seek(0)
    
    return pn.widgets.FileDownload(
        sio,
        filename=f"ET_data_{watershed}_{year}.csv",
        button_type="success",
        label="📥 Download ET Data"
    )

@pn.depends(watershed_dropdown, year_dropdown)
def download_discharge_button(watershed, year):
    """Download button for discharge/runoff data"""
    if watershed not in watershed_discharge_dfs or year is None:
        return pn.pane.Markdown("*Select watershed and year*")
    
    df = watershed_discharge_dfs[watershed]
    df_full = (
        df[df['year'] == year]
        .sort_values('Date')
        .reset_index(drop=True)
    )
    
    if df_full.empty:
        return pn.pane.Markdown("*No discharge data available*")
    
    # 🔹 Only include the discharge columns that are plotted
    discharge_cols = ['USGS_Runoff_cms', 'Runoff_No_ET_cms', 'Runoff_MODIS_ET_cms', 'Runoff_NOAH_ET_cms']
    available_cols = ['Date'] + [col for col in discharge_cols if col in df_full.columns]
    
    df_download = df_full[available_cols].copy()
    df_download['Date'] = df_download['Date'].dt.strftime('%Y-%m-%d')
    
    import io
    sio = io.StringIO()
    df_download.to_csv(sio, index=False)
    sio.seek(0)
    
    return pn.widgets.FileDownload(
        sio,
        filename=f"Discharge_data_{watershed}_{year}.csv",
        button_type="primary",
        label="📥 Download Discharge Data"
    )

@pn.depends(watershed_dropdown, year_dropdown)
def download_all_button(watershed, year):
    """Download button for both ET and discharge data as a ZIP file"""
    if watershed not in watershed_dfs or year is None:
        return pn.pane.Markdown("*Select watershed and year*")
    
    # Check if both datasets are available
    has_et = watershed in watershed_dfs
    has_discharge = watershed in watershed_discharge_dfs
    
    if not has_et and not has_discharge:
        return pn.pane.Markdown("*No data available*")
    
    import io
    import zipfile
    
    # Create a ZIP file in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add ET data if available
        if has_et:
            df_et = watershed_dfs[watershed]
            df_et_year = df_et[df_et['year'] == year].sort_values('Date').reset_index(drop=True)
            
            if not df_et_year.empty:
                df_et_download = df_et_year.copy()
                df_et_download['Date'] = df_et_download['Date'].dt.strftime('%Y-%m-%d')
                df_et_download = df_et_download.drop(columns=['year'])
                
                et_csv = df_et_download.to_csv(index=False)
                zip_file.writestr(f"ET_data_{watershed}_{year}.csv", et_csv)
        
        # Add discharge data if available (only discharge columns)
        if has_discharge:
            df_discharge = watershed_discharge_dfs[watershed]
            df_discharge_year = df_discharge[df_discharge['year'] == year].sort_values('Date').reset_index(drop=True)
            
            if not df_discharge_year.empty:
                # 🔹 Only include the discharge columns that are plotted
                discharge_cols = ['USGS_Runoff_cms', 'Runoff_No_ET_cms', 'Runoff_MODIS_ET_cms', 'Runoff_NOAH_ET_cms']
                available_cols = ['Date'] + [col for col in discharge_cols if col in df_discharge_year.columns]
                
                df_discharge_download = df_discharge_year[available_cols].copy()
                df_discharge_download['Date'] = df_discharge_download['Date'].dt.strftime('%Y-%m-%d')
                
                discharge_csv = df_discharge_download.to_csv(index=False)
                zip_file.writestr(f"Discharge_data_{watershed}_{year}.csv", discharge_csv)
    
    zip_buffer.seek(0)
    
    return pn.widgets.FileDownload(
        zip_buffer,
        filename=f"All_data_{watershed}_{year}.zip",
        button_type="warning",
        label="📦 Download All Data (ZIP)"
    )

# 6. Template layout
template = pn.template.FastListTemplate(
    title='Watershed ET Dashboard',
    sidebar=[
        pn.pane.Markdown("## ET Time Series"),
        pn.pane.Markdown("Daily ET from AnnAGNPS, MODIS, and Noah LSM."),
        pn.pane.Markdown("**Click legend items to show/hide data series**"),
        pn.pane.Markdown("### Settings"),
        pn.pane.Markdown("**Select watershed**"),
        watershed_dropdown,
        pn.pane.Markdown("**Select year**"),
        year_dropdown,
        pn.pane.Markdown("---"),  # Divider
        pn.pane.Markdown("### Download Data"),
        pn.pane.Markdown("*Download data for selected watershed and year*"),
        download_et_button,
        download_discharge_button,
        pn.pane.Markdown("---"),  # Divider
        download_all_button,
    ],
    main=[
        # First row: ET plot and table
        pn.Row(
            pn.Column(
                et_plot,
                margin=(0, 25)
            ),
            pn.Column(
                pn.pane.Markdown("#### First 20 rows (preview)"),
                et_table,
                margin=(0, 25)
            )
        ),
        pn.layout.Divider(),
        # Second row: Map and Discharge plot side by side
        pn.Row(
            pn.Column(
                pn.pane.Markdown("## Watershed Map"),
                pn.Row(
                    pn.pane.Markdown("**Select field to visualize:**"),
                    field_selector,
                    margin=(5, 10)
                ),
                watershed_map,
                margin=(10, 25)
            ),
            pn.Column(
                pn.pane.Markdown("## Discharge Comparison"),
                pn.pane.Markdown("*Observed Runoff vs Model Results*"),
                discharge_plot,
                margin=(10, 25)
            )
        )
    ],
    accent_base_color="#88d8b0",
    header_background="#88d8b0",
)

template.servable()

# panel serve dashboard_fixed.py --show --autoreload

