"""Shared CLI/UI workflows; grouping is a view and never a storage setting."""

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from .config import Config
from .export.transcripts import ExportReport, export_files, group_size, selected_formats
from .ingest.adapter import MetadataAdapter
from .ingest.captions import CaptionAdapter, CaptionError, select_track
from .ingest.discovery import Manifest, discover
from .ingest.transcripts import Result, TranscriptStore, ingest


@dataclass(frozen=True)
class ScrapeReport:
    manifest: Manifest
    ingestions: tuple[Result, ...]
    exports: ExportReport

    @property
    def has_errors(self) -> bool:
        return (any(source.issues for source in self.manifest.sources) or
                any(result.status != 'succeeded' for result in self.ingestions))

    def to_dict(self) -> dict:
        return {'manifest': self.manifest.to_dict(),
                'ingestions': [asdict(result) for result in self.ingestions],
                'exports': self.exports.to_dict(), 'has_errors': self.has_errors}


def export(config: Config, *, formats: Iterable[str] = ('markdown',),
           grouping: int | str = 1, video_ids: Iterable[str] | None = None) -> ExportReport:
    return export_files(config.database, config.output_dir, formats=formats,
                        grouping=grouping, video_ids=video_ids)


def scrape(config: Config, urls: str | Iterable[str], *, limit: int | None = None,
           order: str = 'source', languages: tuple[str, ...] = ('en',), preference: str = 'manual',
           grouping: int | str = 1, formats: Iterable[str] = ('markdown',),
           retry_failed: bool = False, metadata_adapter: MetadataAdapter | None = None,
           caption_adapter: CaptionAdapter | None = None) -> ScrapeReport:
    # Validate user choices before any remote access or storage effects.
    grouping = group_size(grouping)
    formats = selected_formats(formats)
    try:
        select_track((), languages, preference)
    except CaptionError:
        pass
    inputs = (urls,) if isinstance(urls, str) else tuple(urls)
    if not inputs:
        raise ValueError('Provide at least one source URL')
    manifest = discover(inputs, adapter=metadata_adapter, limit=limit, order=order)
    store = TranscriptStore(config.database, config.data_dir / 'canonical')
    results = ingest(manifest, store, adapter=caption_adapter, languages=languages,
                     preference=preference, retry_failed=retry_failed)
    # Even when a JSON projection failed, its committed SQLite transcript is exportable.
    identifiers = tuple(result.video_id for result in results
                        if result.status in {'succeeded', 'projection_failed'})
    exports = export(config, grouping=grouping, formats=formats, video_ids=identifiers)
    return ScrapeReport(manifest, results, exports)
