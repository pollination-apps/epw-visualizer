import pathlib

import streamlit as st
from ladybug.epw import EPW
from ladybug.wea import Wea
from ladybug.sunpath import Sunpath

import ladybug_charts
import ladybug_vtk

from pollination_streamlit_viewer import viewer

# recipe inputs tab
import json
import requests
from pollination_streamlit.selectors import get_api_client
from pollination_streamlit_io import (recipe_inputs_form, select_recipe, study_card, select_study, select_run, select_cloud_artifact)

st.set_page_config(
    page_title='epw visualization',
    layout='centered'
)

# for interacting with Pollination Cloud
api_client = get_api_client()

# project owner & project
project_owner = 'ladybug-tools'
project_name = 'demo'

if 'test' not in st.session_state:
    st.session_state['test'] = None

@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def load_epw(epw_file):
    epw = EPW(epw_file.as_posix())
    return epw

# @st.cache(allow_output_mutation=True, suppress_st_warning=True)
def create_wea(epw_file: str, folder: pathlib.Path):
    epw = load_epw(epw_file)
    fp = folder.joinpath(f'{epw.location.city}.wea')
    epw.to_wea(fp.as_posix())
    
    # upload wea to pollination cloud and store FileMeta for use in the Recipe
    response = api_client.get(
        path=f'/projects/{project_owner}/{project_name}/artifacts',
        params={
            "key": "weather.wea",
        }
    )

    st.session_state['test'] = response

    # https://api.pollination.cloud/docs#/Artifacts/create_artifact
    return fp


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def create_charts(epw_file):
    epw = load_epw(epw_file=epw_file)
    location = epw.location

    # # write the information to the app
    st.write(f'#### City: {location.city}')
    st.write(f'#### Latitude: {location.latitude}')

    dbt = epw.dry_bulb_temperature.heat_map()
    diurnal_chart = epw.diurnal_average_chart()

    return dbt, diurnal_chart


st.write('# Early Design App')
epw_viz_tab, sunpath_tab, direct_sunlight_tab = \
    st.tabs(['Weather data', 'Sunpath', 'Direct sunlight'])

epw_file = None
__here__ = pathlib.Path(__file__)
current_folder = __here__.parent
temp_folder = current_folder.joinpath('temp')
temp_folder.mkdir(parents=True, exist_ok=True)

with epw_viz_tab:
    epw_content = st.sidebar.file_uploader(
        'Upload your .epw file',
        type=['epw'],
        help='Upload a custom epw file from your computer. You can down an epw file from '
        'THE Internet!',
        )

    if epw_content:
        # 1. figure out the file name based on the input file
        file_name = epw_content.name
        # 2. write the file to the app - probably under a folder
        epw_file = temp_folder.joinpath(file_name)
        # 3. path the new file to the epw reader
        epw_file.write_bytes(epw_content.read())
    else:
        epw_file = current_folder.joinpath('chicago.epw')

    dbt, diurnal_chart = create_charts(epw_file)

    st.plotly_chart(diurnal_chart, use_container_width=True)
    st.plotly_chart(dbt, use_container_width=True)

with sunpath_tab:
    if epw_file:
        epw = load_epw(epw_file)
        sunpath = Sunpath.from_location(epw.location)
        sunpath_vtkjs = sunpath.to_vtkjs(
            temp_folder, file_name=f'{epw.location.city}_sunpath',
            radius=100
        )

        # sunpath.to_vis_set()

        # view the 3D sunpath
        viewer(key='sunpath-viewer', content=sunpath_vtkjs.read_bytes())

with direct_sunlight_tab:

    direct_sun_hours = open('files/direct_sunlight_hours.json')
    default_recipe_inputs = open('files/default_recipe_inputs.json')

    # create a wea file
    wea_file = create_wea(epw_file, temp_folder)

    # add the rest of the code here
    # st.write(f'The wea file is written to: {wea_file}.')

    st.header('Create a new study on Pollination Cloud')
    st.info("""Select a Recipe, enter inputs and create a study. View the new study, or any previously created study under the View Study tab.""")

    # Content that will be viewed by pollination-viewer
    if 'response' not in st.session_state:
        st.session_state['response'] = None
    
    if 'extension' not in st.session_state:
        st.session_state['extension'] = None
    
    recipe = select_recipe(
        'sel-recipe',
        api_client,
        project_owner=project_owner,
        project_name=project_name,
        default_recipe=json.load(direct_sun_hours),
    )

    # Recipe inputs form
    study = recipe_inputs_form(
        'recipe-study',
        api_client,
        project_owner=project_owner,
        project_name=project_name,
        recipe=recipe,
        default_inputs=json.load(default_recipe_inputs),
    )

    if study is not None and 'id' in study:
        sel_study = select_study(
            'sel-study',
            api_client,
            project_name=project_name,
            project_owner=project_owner,
            default_study_id=study['id'],
        )

        if sel_study is not None:
            study_card(
                'study-card',
                api_client,
                project_name=project_name,
                project_owner=project_owner,
                study=sel_study,
                run_list=True,
            )

            # sel_run = select_run(
            #     'sel-run',
            #     api_client,
            #     project_name=project_name,
            #     project_owner=project_owner,
            #     job_id=sel_study['id']
            # )
            
            # Fetch the artifact contents on selection
            def handle_sel_artifact():
                artifact = st.session_state['sel-artifact']
                
                if artifact is None:
                    st.session_state['content'] = None
                    st.session_state['extension'] = None
                    return
                
                request_params = artifact['key']

                request_path = [
                    'projects',
                    project_owner,
                    project_name,
                    'jobs',
                    sel_study['id'],
                    'artifacts'
                ]
                url = "/".join(request_path)

                signed_url = api_client.get(path=f'/{url}/download', params=request_params)

                response = requests.get(signed_url, headers=api_client.headers)

                if response.status_code is 200:
                    st.session_state['response'] = response.content
                    # if file is viewable by viewer, prepare vtkjs file
                    extension = artifact['file_name'].split('.')[1] if st.session_state['sel-artifact'] else None
                    st.session_state['extension'] = extension
                        

            sel_artifact = select_cloud_artifact(
                'sel-artifact',
                api_client,
                project_name=project_name,
                project_owner=project_owner,
                study_id=sel_study['id'],
                file_name_match=".*",
                on_change=handle_sel_artifact
            )

            st.download_button(
                key='download-button',
                label='Download File', 
                data=st.session_state['response'], 
                file_name=sel_artifact['name'] if sel_artifact is not None else 'download.zip', 
                disabled=st.session_state['response'] == None
            )

            if st.session_state['extension'] == 'vtkjs':
                vtkjs = viewer(
                    "pollination-viewer",
                    content=st.session_state['response'],
                )

st.json(st.session_state['test'] or '{}')