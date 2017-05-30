#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""subcommands.py

Provides subcommand functions for the pdp.py script

- config:        interact with config files
- prodigal:      run prodigal bacterial gene prediction
- eprimer3:      predict primers with EMBOSS ePrimer3
- primersearch:  run in-silico hybridisation with EMBOSS PrimerSearch
- blastscreen:   screen primers with BLASTN
- classify:      classify primers

(c) The James Hutton Institute 2017

Author: Leighton Pritchard
Contact: leighton.pritchard@hutton.ac.uk

Leighton Pritchard,
Information and Computing Sciences,
James Hutton Institute,
Errol Road,
Invergowrie,
Dundee,
DD6 9LH,
Scotland,
UK

The MIT License

Copyright (c) 2017 The James Hutton Institute
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import os

from diagnostic_primers import (prodigal, eprimer3, blast)

from .tools import (log_clines, run_parallel_jobs,
                    load_config_tab, load_config_json)


def subcmd_config(args, logger):
    """Run `config` subcommand operations.

    Available subcommands:

    - to_json: convert .tab format config file to JSON and write out
    - validate: report on the status of sequence files/classes
    - fix_sequences: stitch multiple sequences together, convert ambiguity
                     symbols to Ns, and write out a new JSON config file

    All subcommands should take either .tab or .json config files,
    distinguished by file extension
    """
    # Determine input config file type
    configtype = os.path.splitext(args.infilename)[-1][1:]
    if configtype not in ('tab', 'json', 'conf'):
        logger.error("Expected config file to end in .conf, .json or .tab " +
                     "got %s (exiting)", configtype)
        raise SystemExit(1)

    if configtype in ('tab', 'conf'):
        coll = load_config_tab(args, logger)
    elif configtype in ('json',):
        coll = load_config_json(args, logger)

    # Do sequences need to be stitched or their ambiguities replaced?
    # If --validate is active, we report only and do not modify.
    # Note that the underlying code doesn't require us to check whether
    # the sequence files need stitching or symbols replacing, and
    # we could more efficiently use
    # for g in gc.data:
    #     g.stitch()
    #     g.replace_ambiguities()
    # but we're being helpfully verbose.
    logger.info('Checking whether input sequences require stitching, ' +
                'or have non-N ambiguities.')
    problems = ["Validation problems"]  # Holds messages about problem files
    for gcc in coll.data:
        if gcc.needs_stitch:
            msg = '%s requires stitch' % gcc.name
            logger.info(msg)
            problems.append('%s (%s)' % (msg, gcc.seqfile))
            if args.fix_sequences:
                gcc.stitch()
        else:
            logger.info('%s does not require stitch', gcc.name)
        if gcc.has_ambiguities:
            msg = '%s has non-N ambiguities' % gcc.name
            logger.info(msg)
            problems.append('%s (%s)' % (msg, gcc.seqfile))
            if args.fix_sequences:
                gcc.replace_ambiguities()
        else:
            logger.info('%s does not contain non-N ambiguities', gcc.name)
        logger.info('Sequence file: %s', gcc.seqfile)

    # If we were not fixing sequences, report problems
    if not args.fix_sequences:
        if len(problems) > 1:
            logger.warning('\n    '.join(problems))

    # Write post-processing config file and exit
    if args.to_json:
        logger.info('Writing JSON config file to %s', args.to_json)
        coll.write_json(args.to_json)
    return 0


def subcmd_prodigal(args, logger):
    """Run Prodigal to predict bacterial CDS on the input sequences."""
    coll = load_config_json(args, logger)

    # Build command-lines for Prodigal and run
    logger.info('Building Prodigal command lines...')
    if args.prodigalforce:
        logger.warning('Forcing Prodigal to run. This may overwrite ' +
                       'existing output.')
    else:
        logger.info('Prodigal will fail if output directory exists')
    clines = prodigal.build_commands(coll, args.prodigal_exe,
                                     args.prodigaldir, args.prodigalforce)
    log_clines(clines, logger)
    run_parallel_jobs(clines, args, logger)

    # Add Prodigal output files to the GenomeData objects and write
    # the config file
    for gcc in coll.data:
        gcc.features = gcc.cmds['prodigal'].split()[-1].strip()
        logger.info('%s feature file:\t%s' % (gcc.name, gcc.features))
    logger.info('Writing new config file to %s' % args.outfilename)
    coll.write(args.outfilename)
    return 0


def subcmd_eprimer3(args, logger):
    """Run ePrimer3 to design primers for each input sequence."""
    coll = load_config_json(args, logger)

    # Build command-lines for ePrimer3 and run
    logger.info('Building ePrimer3 command lines...')
    if args.eprimer3_force:
        logger.warning('Forcing ePrimer3 to run. This may overwrite ' +
                       'existing output.')
    else:
        logger.info('ePrimer3 may fail if output directory exists')
    clines = eprimer3.build_commands(coll, args.eprimer3_exe,
                                     args.eprimer3_dir,
                                     args.eprimer3_force, vars(args))
    pretty_clines = [str(c).replace(' -', '\\\n\t\t-') for c in clines]
    log_clines(pretty_clines, logger)
    run_parallel_jobs(clines, args, logger)

    # Load ePrimer3 data for each input sequence, and write JSON representation
    # Record JSON representation in the object
    for gcc in coll.data:
        logger.info("Loading/naming primers in %s" %
                    gcc.cmds['ePrimer3'].outfile)
        primers, outfname = eprimer3.load_primers(gcc.cmds['ePrimer3'].outfile)
        logger.info('Named primers ePrimer3 file created:\t%s' % outfname)
        outfname = os.path.splitext(outfname)[0] + '.json'
        logger.info('Writing primers to %s' % outfname)
        eprimer3.primers_to_json(primers, outfname)
        gcc.primers = outfname

    logger.info('Writing new config file to %s' % args.outfilename)
    coll.write(args.outfilename)
    return 0


def subcmd_primersearch(args, logger):
    """Perform in silico hybridisation with EMBOSS PrimerSearch."""
    args = args
    logger = logger
    raise NotImplementedError


def subcmd_blastscreen(args, logger):
    """Screen primer sequences against a local BLAST database."""
    # We can't go on if there's no BLASTN+ database to check against
    if args.bs_db is None:
        logger.error("No BLASTN+ database provided, cannot perform " +
                     "screen (exiting)")
        return 1

    coll = load_config_json(args, logger)

    for gcc in coll.data:
        logger.info("Loading primer data from %s" % gcc.primers)
        gcc.fastafname = eprimer3.json_to_fasta(gcc.primers)
        logger.info("Wrote primer FASTA sequences to %s" % gcc.fastafname)

    logger.info("Building BLASTN screen command-lines...")
    if args.bs_force:
        logger.warning("Forcing BLASTN screen to run. This may " +
                       "overwrite existing output.")
    else:
        logger.info("BLASTN screen may fail if output directory exists.")
    clines = blast.build_commands(coll,
                                  args.bs_db, args.bs_exe,
                                  args.bs_dir, args.bs_force)
    pretty_clines = [str(c).replace(' -', '\\\n\t\t-') for c in clines]
    log_clines(pretty_clines, logger)
    run_parallel_jobs(clines, args, logger)

    logger.info("BLASTN+ screen complete")
    return 0


def subcmd_classify(args, logger):
    """Perform classification of predicted primers."""
    args = args
    logger = logger
    raise NotImplementedError
