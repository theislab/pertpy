from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, Union

import numpy as np
import pandas as pd
import pubchempy as pcp
from rich import print
from scanpy import settings

from pertpy.data._dataloader import _download

from ._look_up import LookUp

if TYPE_CHECKING:
    from anndata import AnnData


class CompoundMetaData:
    """Utilities to fetch metadata for compound."""

    def __init__(self):
        settings.cachedir = ".pertpy_cache"

    def annotate_compound(
        self,
        adata: AnnData,
        query_id: str = "perturbation",
        query_id_type: Literal["name", "cid"] = "name",
        show: int | str = 5,
        copy: bool = False,
    ) -> AnnData:
        """Fetch compound annotation.

        For each cell, we fetch compound annotation via pubchempy.

        Args:
            adata: The data object to annotate.
            query_id: The column of `.obs` with compound identifiers. Defaults to "perturbation".
            query_id_type: The type of compound identifiers, name or cid. Defaults to "name".
            show: The number of unmatched identifiers to print, can be either non-negative values or "all". Defaults to 5.
            copy: Determines whether a copy of the `adata` is returned. Defaults to False.

        Returns:
            Returns an AnnData object with compound annotation.

        """
        if copy:
            adata = adata.copy()

        if query_id not in adata.obs.columns:
            raise ValueError(f"The requested query_id {query_id} is not in `adata.obs`. \n" "Please check again. ")

        query_dict = {}
        not_matched_identifiers = []
        for p in adata.obs[query_id].dropna().astype(str).unique():
            if query_id_type == "name":
                cids = pcp.get_compounds(p, "name")
                if len(cids) == 0:  # search did not work
                    not_matched_identifiers.append(p)
                if len(cids) >= 1:
                    # If the name matches the first synonym offered by PubChem (outside of capitalization),
                    # it is not changed (outside of capitalization). Otherwise, it is replaced with the first synonym.
                    query_dict[p] = [cids[0].synonyms[0], cids[0].cid, cids[0].canonical_smiles]
            else:
                try:
                    cid = pcp.Compound.from_cid(p)
                    query_dict[p] = [cid.synonyms[0], p, cid.canonical_smiles]
                except pcp.BadRequestError:
                    # pubchempy throws badrequest if a cid is not found
                    not_matched_identifiers.append(p)

        identifier_num_all = len(adata.obs[query_id].unique())
        if len(not_matched_identifiers) == identifier_num_all:
            raise ValueError(
                f"Attempting to find the query id {query_id} in the adata.obs in pubchem database.\n"
                "However, none of them could be found.\n"
                "The annotation process has been halted.\n"
                "To resolve this issue, please call the `CompoundMetaData.lookup()` function to create a LookUp object.\n"
                "By using the `LookUp.compound()` method. "
            )

        if len(not_matched_identifiers) > 0:
            if isinstance(show, str):
                if show != "all":
                    raise ValueError("Only a non-positive value or all is accepted.")
                else:
                    show = len(not_matched_identifiers)

            if isinstance(show, int) and show >= 0:
                show = min(show, len(not_matched_identifiers))
                print(
                    f"[bold yellow]There are {identifier_num_all} identifiers in `adata.obs`. "
                    f"However {len(not_matched_identifiers)} identifiers can't be found in the compound annotation, "
                    "leading to the presence of NA values for their respective metadata. Please check again: ",
                    *not_matched_identifiers[:show],
                    sep="\n- ",
                )
            else:
                raise ValueError("Only 'all' or a non-positive value is accepted.")

        query_df = pd.DataFrame.from_dict(query_dict, orient="index", columns=["pubchem_name", "pubchem_ID", "smiles"])
        adata.obs = adata.obs.merge(
            query_df, left_on=query_id, right_index=True, how="left", suffixes=("", "_fromMeta")
        )
        # Remove duplicate columns
        if query_id_type == "cid":
            duplicate_col = "pubchem_ID" if query_id != "pubchem_ID" else "pubchem_ID_fromMeta"
            adata.obs.drop(duplicate_col, axis=1, inplace=True)
        else:
            # Column is converted to float after merging due to unmatches
            # Convert back to integers
            adata.obs.pubchem_ID = adata.obs.pubchem_ID.astype("Int64")
        return adata
