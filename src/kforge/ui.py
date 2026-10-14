"""Optional local Streamlit entrypoint; services also power the CLI."""

import sqlite3

from kforge.config import load_config
from kforge.ingest.urls import parse_url_list
from kforge import workflows


def render(st):
    st.set_page_config(page_title='Knowledge Foundry', page_icon='📚', layout='wide')
    st.title('Knowledge Foundry')
    st.caption('Collect authorized video captions and export stored transcripts.')
    try:
        config = load_config()
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return
    identity = (str(config.database), str(config.output_dir))
    if st.session_state.get('storage_identity') != identity:
        st.session_state['storage_identity'] = identity
        st.session_state.pop('last_scrape', None)
        st.session_state.pop('last_export', None)
    with st.form('scrape'):
        st.subheader('Collect captions')
        urls = st.text_area('Sources', help='One authorized YouTube video, playlist or channel URL per line.',
                            key='sources')
        limit = st.number_input('Video limit', min_value=0, max_value=1000, value=10, step=1, key='limit')
        languages = st.text_input('Preferred languages', value='en',
                                  help='Comma-separated codes in priority order, for example de,en.', key='languages')
        preference = st.selectbox('Transcript preference', ('manual', 'auto'), key='preference')
        grouping = st.text_input('Export group size', value='1', help='1, a positive number, or all.',
                                 key='scrape_group')
        formats = st.multiselect('Export formats', ('markdown', 'txt', 'jsonl'), default=['markdown'],
                                key='scrape_formats')
        retry_failed = st.checkbox('Retry previously failed captions', key='retry_failed')
        collect = st.form_submit_button('Collect and export')
    if collect:
        # A new attempt clears old success output, so a failure cannot look successful.
        st.session_state.pop('last_scrape', None)
        st.session_state.pop('last_export', None)
        try:
            with st.spinner('Collecting captions…'):
                report = workflows.scrape(config, parse_url_list(urls), limit=int(limit),
                    languages=tuple(value.strip() for value in languages.split(',')),
                    preference=preference, grouping=grouping, formats=formats,
                    retry_failed=retry_failed)
            st.session_state['last_scrape'] = report.to_dict()
            st.session_state['last_export'] = report.exports.to_dict()
        except (OSError, UnicodeError, sqlite3.Error, ValueError, RuntimeError) as exc:
            st.error(str(exc))
    with st.form('export'):
        st.subheader('Export stored transcripts offline')
        offline_group = st.text_input('Stored transcript group size', value='1', key='offline_group')
        offline_formats = st.multiselect('Stored transcript formats', ('markdown', 'txt', 'jsonl'),
                                         default=['markdown'], key='offline_formats')
        export = st.form_submit_button('Export stored transcripts')
    if export:
        st.session_state.pop('last_export', None)
        try:
            report = workflows.export(config, grouping=offline_group, formats=offline_formats)
            st.session_state['last_export'] = report.to_dict()
        except (OSError, UnicodeError, sqlite3.Error, ValueError, RuntimeError) as exc:
            st.error(str(exc))
    scrape = st.session_state.get('last_scrape')
    if scrape is not None:
        st.subheader('Collection status')
        if scrape['has_errors']:
            st.warning('Some sources or captions failed. Successful transcripts were retained.')
        else:
            st.success('Collection completed.')
        st.dataframe([{'source': source['input_url'], 'status': source['status'],
                       'issues': ', '.join(issue['code'] for issue in source['issues'])}
                      for source in scrape['manifest']['sources']])
        st.dataframe([{'video': result['video_id'], 'status': result['status'],
                       'attempts': result['attempts'],
                       'issue': result['issue']['code'] if result['issue'] else ''}
                      for result in scrape['ingestions']])
    exported = st.session_state.get('last_export')
    if exported is not None:
        st.subheader('Export status')
        if exported['video_count'] == 0:
            st.info('No stored transcripts matched this export.')
        else:
            st.success(f"Exported {exported['video_count']} videos into {len(exported['artifacts'])} files.")
            st.dataframe([{'file': artifact['path'], 'format': artifact['format'],
                           'videos': len(artifact['video_ids'])} for artifact in exported['artifacts']])
        st.caption('Exports contain source text and provenance. Claims remain unverified; confidence is unknown.')


if __name__ == '__main__':
    import streamlit as st
    render(st)
