from Bio import Entrez, SeqIO
import subprocess
import glob
import os

import defaults
import utils

import logging

def get_species_name_from_file(taxid_file: str,
                               _entrez_email: str = defaults.ENTREZ_EMAIL,
                               _entrez_api_token: str = defaults.NCBI_API_TOKEN) -> str:
    """
    Given a taxid number, return the scientific name of the species in the format Genus_species. Used
    in [taxlist2name]. If the file name is not a valid taxid, return the same file name.
    If the queried taxid is not found, return the tax-id.

        Parameters
        ----------
            :param taxid_file: Taxonomic ID-named file.
            :param _entrez_email: Email address for Entrez.
            :param _entrez_api_token: API token for Ent.

        Returns
        -------
            :returns: Scientific name in the format Genus_species

    """
    Entrez.email = _entrez_email
    Entrez.api_key = _entrez_api_token
    taxid_file_query = taxid_file.split('.')[0]
    try:
        taxid_file_query = int(taxid_file_query)
        handle = Entrez.efetch(db="taxonomy", id=str(taxid_file_query), retmode="xml")
        records = Entrez.read(handle)
        handle.close()

        if not records:
            logging.warning(f'Taxid {taxid_file} not found.')
            return str(taxid_file_query)

        scientific_name = records[0]['ScientificName']
        return scientific_name.replace(" ", "_")

    except ValueError:
        logging.warning(f'Invalid taxid {taxid_file_query}. Generating folder with the same name.')
        return taxid_file_query


def taxlist2name(taxid_list: list) -> list:
    """
    Given a list of taxids, return the scientific names of the species in the format Genus_species.

        Parameters
        ----------
            :param taxid_list: List of taxonomic IDs.

        Returns
        -------
            :returns: List of scientific names in the format Genus_species.

    """
    return [get_species_name_from_file(taxid) for taxid in taxid_list]


def blast_db_generator(input_file_path,
                       output_directory_path,
                       db_name: str,
                       db_type: str) -> None:
    """
    Generates the BLAST databases from the FASTA files from the specified file.

        Parameters
        ----------
            :param input_file_path: The input FASTA file.
            :param output_directory_path: The output directory path for the BLAST database.
            :param db_name: The name of the database.
            :param db_type: The type of database to generate.


    """
    makeblastdb_command = ['makeblastdb',
                           '-in', input_file_path,
                           '-dbtype', db_type,
                           '-out', os.path.join(output_directory_path, db_name)]

    subprocess.run(makeblastdb_command)
    logging.info(f'Generated BLAST database for {db_name}.')


def directory_db_generator(file_list: list,
                           input_db,
                           db_type: str,
                           tax_id_input: bool,
                           output_directory_path,
                           max_attempts: int = defaults.MAX_RETRIEVAL_ATTEMPTS,
                           display_warning: bool = defaults.DISPLAY_REQUESTS_WARNING,
                           force_rerun: bool = False) -> list:
    """
    Generates the BLAST databases from the FASTA files in the specified directory. It also checks if the directory
    containing each database already exists to avoid re-generating them.

        Parameters
        ----------
            :param file_list: The list of files in the input directory (tax-id named).
            :param input_db: The path to the directory where the tax-id named FASTA files are stored.
            :param db_type: The type of database to generate (nucl, prot).
            :param tax_id_input: Boolean flag to indicate if the input file name is tax-id or string (Use with LTRh).
            :param output_directory_path: The output directory path for the BLAST databases.
            :param max_attempts: Number of retry attempts for the species name retrieval.
            :param display_warning: Boolean flag to enable or disable logging of HTTP request warnings.
            :param force_rerun: Boolean flag to force re-running of all files, even if the database already exists.

        Returns
        -------
            :return: List of generated genomes.

    """
    genomes = []
    directory_list = [f for f in os.listdir(output_directory_path) if os.path.isdir(os.path.join(output_directory_path, f))]

    # Check that within the directory_list folders, there is a file with the .ndb extension
    valid_directories = []
    for directory in directory_list:
        if ndb_files := glob.glob(os.path.join(output_directory_path, directory, '*.ndb')):
            if not force_rerun:
                logging.info(f'{directory} already contains a .ndb file. Skipping.')
            valid_directories.append(directory)

    for file in file_list:
        sc_name = None
        for attempt in range(max_attempts):
            try:
                sc_name = get_species_name_from_file(file.split('.')[0])
                break  # Break the loop if successful
            except Exception as e:
                if display_warning:
                    logging.warning(f"Attempt {attempt + 1} to retrieve species name for {file} failed: {e}")
                if attempt == max_attempts - 1:
                    logging.warning(f"Failed to retrieve species name for {file} after {max_attempts} retries.")
                    raise RuntimeError(
                        f"Failed to retrieve species name for {file} after {max_attempts} retries."
                    ) from e

        # Skip if the species directory exists and has the .ndb file, unless force_rerun is True
        if sc_name in valid_directories and not force_rerun:
            logging.info(f'{sc_name.replace("_", " ")} database already exists. Skipping.')
            continue

        # Generate the directory for the database
        directory = utils.directory_generator(output_directory_path, sc_name)

        if tax_id_input:
            blast_db_generator(input_file_path=os.path.join(input_db, file),
                               output_directory_path=directory,
                               db_name=sc_name,
                               db_type=db_type)
        else:
            blast_db_generator(input_file_path=os.path.join(input_db, f'{sc_name}.fasta'),
                               output_directory_path=directory,
                               db_name=sc_name,
                               db_type=db_type)

        genomes.append(sc_name)

    return genomes



def objdict2fasta(object_dict: dict,
                  output_directory_path: os.PathLike,
                  output_file_name: str) -> None:
    """
    Converts the object dictionary to a single concatenated FASTA file in the specified directory.

        Parameters
        ----------
            :param object_dict: The dictionary containing the object pairs.
            :param output_directory_path: The output directory path for the FASTA file.
            :param output_filename: The name of the output concatenated FASTA file.
    """
    output_file_path = os.path.join(output_directory_path, output_file_name)

    with open(output_file_path, 'w') as concatenated_fasta:
        for key, obj in object_dict.items():
            SeqIO.write(obj.get_fasta('seqrecord'), concatenated_fasta, 'fasta')
            logging.info(f'Extracted FASTA from {key} and appended to {output_file_name}.')


def ltr_index_generator(input_directory_path: str,
                        file_list: list,
                        max_attempts: int = defaults.MAX_RETRIEVAL_ATTEMPTS,
                        display_warning: bool = defaults.DISPLAY_REQUESTS_WARNING,
                        force_rerun: bool = False) -> None:
    """
    Generates the Suffixerator index for the LTRHarvest analysis.

        Parameters
        ----------
            :param input_directory_path: The path to the directory containing the FASTA files.
            :param file_list: The list of files in the input directory (tax-id named).
            :param max_attempts: Number of retry attempts for the species name retrieval.
            :param display_warning: Boolean flag to enable or disable logging of HTTP request warnings.
            :param force_rerun: Boolean flag to force re-running of all files, even if an index already exists.
    """
    directory_list = [f for f in os.listdir(input_directory_path) if os.path.isdir(os.path.join(input_directory_path, f))]

    # Check that within the directory_list folders, there is a file with the .esq extension
    valid_directories = []
    for directory in directory_list:
        if esq_files := glob.glob(os.path.join(input_directory_path, directory, '*.esq')):
            # if not force_rerun:
            #     logging.info(f'{directory} already contains a .esq file.')
            valid_directories.append(directory)

    # TODO: TRANSFER RETRY LOGIC TO [get_species_name_from_file]
    for file in file_list:
        sc_name = None
        for attempt in range(max_attempts):
            try:
                sc_name = get_species_name_from_file(file.split('.')[0])
                break  # Break the loop if successful
            except Exception as e:
                if display_warning:
                    logging.warning(f"Attempt {attempt + 1} to retrieve species name for {file} failed: {e}")
                if attempt == max_attempts - 1:
                    raise RuntimeError(
                        f"Failed to retrieve species name for {file} after {max_attempts} retries."
                    ) from e

        # Skip if the species directory exists and has the .esq file, unless force_rerun is True
        if sc_name in valid_directories and not force_rerun:
           logging.info(f'{sc_name.replace("_", " ")} index already exists. Skipping.')
           continue

        # Generate the Suffixerator index
        if sc_name in defaults.SPECIES:
            suffixerator_command = ['gt', 'suffixerator',
                                    '-db', os.path.join(input_directory_path, file),
                                    '-indexname', os.path.join(input_directory_path, sc_name, sc_name),
                                    '-tis', '-suf', '-lcp', '-des', '-ssp', '-sds', '-dna', '-v']

            subprocess.run(suffixerator_command)
            logging.info(f'Generated LTRHarvest Index for {sc_name}.')



def ltr_harvester(index_directory_path: str,
                  file_list: list,
                  output_directory_path: str,
                  max_attempts: int = defaults.MAX_RETRIEVAL_ATTEMPTS,
                  display_warning: bool = defaults.DISPLAY_REQUESTS_WARNING,
                  force_rerun: bool = False) -> None:
    """
    Performs the LTRHarvest analysis on the specified directory.

        Parameters
        ----------
            :param index_directory_path: The path to the directory containing the index files.
            :param file_list: The list of files in the input directory (tax-id named).
            :param output_directory_path: The path to the output directory for the LTRHarvest results.
            :param max_attempts: Number of retry attempts for the species name retrieval.
            :param display_warning: Boolean flag to enable or disable logging of HTTP request warnings.
            :param force_rerun: Boolean flag to force re-running of all files, even if output files already exist.
    """
    # Build a list of existing output fasta files
    existing_fasta_files = glob.glob(os.path.join(output_directory_path, '*.fasta'))
    existing_species = [os.path.splitext(os.path.basename(f))[0] for f in existing_fasta_files]

    for file in file_list:
        sc_name = None
        for attempt in range(max_attempts):
            try:
                sc_name = get_species_name_from_file(file.split('.')[0])
                break  # Break the loop if successful
            except Exception as e:
                if display_warning:
                    logging.warning(f"Attempt {attempt + 1} to retrieve species name for {file} failed: {e}")
                if attempt == max_attempts - 1:
                    raise RuntimeError(
                        f"Failed to retrieve species name for {file} after {max_attempts} retries."
                    ) from e

        # Skip if the output fasta file exists and not force_rerun
        if sc_name in existing_species and not force_rerun:
            logging.info(f'LTRHarvest output for {sc_name.replace("_", " ")} already exists. Skipping.')
            continue

        # Generate the LTRHarvest output
        if sc_name in defaults.SPECIES:
            ltrharvest_command = ['gt', 'ltrharvest',
                                  '-index', os.path.join(index_directory_path, sc_name, sc_name),
                                  '-out', os.path.join(output_directory_path, f'{sc_name}.fasta'),
                                  '-gff3', os.path.join(output_directory_path, f'{sc_name}.gff')]

            subprocess.run(ltrharvest_command)
            logging.info(f'Generated LTRHarvest output for {sc_name}.')


