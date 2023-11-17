from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, Union

import pandas as pd
import numpy as np
from rich import print
from scanpy import settings

from pertpy.data._dataloader import _download

from ._look_up import LookUp

if TYPE_CHECKING:
    from anndata import AnnData


class MoaMetaData:
    """Utilities to fetch metadata for mechanism of action studies."""

    def __init__(self):
        settings.cachedir = ".pertpy_cache"
        moa_file_path = settings.cachedir.__str__() + "/repurposing_drugs_20200324.txt"
        if not Path(moa_file_path).exists():
            print(
                "[bold yellow]No metadata file was found for mechanism of action (MoA) studies."
                " Starting download now."
            )
            _download(
                url="https://s3.amazonaws.com/data.clue.io/repurposing/downloads/repurposing_drugs_20200324.txt",
                output_file_name="repurposing_drugs_20200324.txt",
                output_path=settings.cachedir,
                block_size=4096,
                is_zip=False,
            )
        self.moa = pd.read_csv(moa_file_path, sep="	", skiprows=9) 
        self.moa = self.moa[["pert_iname", "moa","target"]]

    def annotate_moa(
        self,
        adata: AnnData,
        query_id: str = "pert_iname",
        target: str | None = None,
        copy: bool = False,
    ) -> AnnData:
        """Fetch MoA annotation.

        For each cell, we fetch mechanism of action annotation sourced from clue.io.

        Args:
            adata: The data object to annotate.
            query_id: The column of `.obs` with perturbation information. Defaults to "pert_iname".
            target: The column of `.obs` with target information. Defaults to None.
            copy: Determines whether a copy of the `adata` is returned. Defaults to False.

        Returns:
            Returns an AnnData object with moa annotation.

        """
        if copy:
            adata = adata.copy()

        if query_id not in adata.obs.columns:
            raise ValueError(f"The requested query_id {query_id} is not in `adata.obs`. \n" "Please check again. ")

        identifier_num_all = len(adata.obs[query_id].unique())
        not_matched_identifiers = list(set(adata.obs[query_id].str.lower()) - set(self.moa["pert_iname"].str.lower()))
        if len(not_matched_identifiers) == identifier_num_all:
            raise ValueError(
                f"Attempting to match the query id {query_id} in the adata.obs to the pert_iname in the metadata.\n"
                "However, none of the query IDs could be found in the moa annotation data.\n"
                "The annotation process has been halted.\n"
                "To resolve this issue, please call the `MoaMetaData.lookup()` function to create a LookUp object.\n"
                "By using the `LookUp.moa()` method. "
            )

        if len(not_matched_identifiers) > 0:
            print(
                f"[bold blue]There are {identifier_num_all} types of perturbation in `adata.obs`."
                f"However, {len(not_matched_identifiers)} can't be found in the moa annotation,"
                "leading to the presence of NA values for their respective metadata.\n",
                "Please check again: ",
                *not_matched_identifiers,
                sep="\n- ",
            )
        adata.obs = adata.obs.merge(self.moa, left_on=adata.obs[query_id].str.lower(), 
                                    right_on=self.moa["pert_iname"].str.lower(), 
                                    how="left", suffixes=("", "_fromMeta")).set_index(adata.obs.index)

        if target is not None:
            target_meta = "target" if target != 'target' else "target_fromMeta"
            adata.obs[target_meta] = adata.obs[target_meta].mask(~adata.obs.apply(lambda row: str(row[target]) in str(row[target_meta]),
                                                                                  axis=1))
            pertname_meta = 'pert_iname' if query_id != 'pert_iname' else 'pert_iname_fromMeta'
            adata.obs.loc[adata.obs[target_meta].isna(), [pertname_meta, 'moa']] = np.nan

        # If query_id and reference_id have different names,
        # there will be a column for each of them after merging,
        # which is redundant as they refer to the same information.
        # We will move the reference_id column.
        if query_id != "pert_iname":
            del adata.obs['pert_iname']
        
        return adata

    def lookup(self) -> LookUp:
        """Generate LookUp object for MoaMetaData.

        The LookUp object provides an overview of the metadata to annotate.
        Each annotate_{metadata} function has a corresponding lookup function in the LookUp object,
        where users can search the reference_id in the metadata and
        compare with the query_id in their own data.

        Returns:
            Returns a LookUp object specific for cell line annotation.
        """
        return LookUp(
            type="cell_line",
            transfer_metadata=[
                self.moa
            ],
        )