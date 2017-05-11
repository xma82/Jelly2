#!/usr/bin/env python

import os
import subprocess
import itertools as it
from string import Template

import pysam
from pyfaidx import Fasta

class Support():
    def __init__(self):
        return
    
    def mapping(self, args):
        basename = '.'.join(args.scaffolds.split('.')[:-1])
        # Run the BLASR mapping jobs
        mapL = {"reads": args.subreads, "flanks": basename+'_gaps.L.fa', "threads": args.threads, "param": args.blasr, "out": "aligned_gaps.L.bam"}
        mapR = {"reads": args.subreads, "flanks": basename+'_gaps.R.fa', "threads": args.threads, "param": args.blasr, "out": "aligned_gaps.R.bam"}
        mappingTemplate = Template("blasr ${reads} ${flanks} --nproc ${threads} --bam --out ${out} --hitPolicy allbest ${param}")
        for job in [mapL, mapR]:
            subprocess.call(mappingTemplate.substitute(job).split(' '))
    
    def sorting(self, args):
        # Sort the BAM alignment files
#        sortL = {"threads": args.threads, "output": "sorted_gaps.L", "input": "aligned_gaps.L.bam"}
#        sortR = {"threads": args.threads, "output": "sorted_gaps.R", "input": "aligned_gaps.R.bam"}
        sortL = ['samtools', 'sort', '-o', 'sorted_gaps.L', '-@', str(args.threads), 'aligned_gaps.L.bam']
        sortR = ['samtools', 'sort', '-o', 'sorted_gaps.R', '-@', str(args.threads), 'aligned_gaps.R.bam']
#        sortingTemplate = Template("samtools sort -T ${output} -@ ${threads} ${input}")
        for job in [sortL, sortR]:
            subprocess.call(job)
    
    def indexing(self, args):
        # Index the BAM alignment files
        indexL = {"aligns": "sorted_gaps.L.bam"}
        indexR = {"aligns": "sorted_gaps.R.bam"}
        indexingTemplate = Template("samtools index ${aligns}")
        for job in [indexL, indexR]:
            subprocess.call(indexingTemplate.substitute(job).split(' '))
    
    def find_support(self, args):
        # Load BAM alignments, gap BED table, reference Fasta file
        basename = '.'.join(args.scaffolds.split('.')[:-1])
        gapsL = pysam.AlignmentFile('sorted_gaps.L.bam', 'rb')
        gapsR = pysam.AlignmentFile('sorted_gaps.R.bam', 'rb')
        gap_list = open(args.gap_info, 'r').read().split('\n')[:-1]
        gap_list = [x.split('\t') for x in gap_list]
        gap_dict = {x[0]: [(x[1], x[2])] if x[0] not in gap_dict else gap_dict[x[0]].append((x[1], x[2])) for x in gap_list}
        ref = Fasta(args.scaffolds)
        # Iterate through scaffolds and determine support
        os.mkdir('Gap_Support')
        supported_gaps = list()
        for scaf in ref:
            # Continue if there are no gaps in scaffold
            try:
                gaps = gap_dict[str(scaf.name)]
            except KeyError:
                continue
            # Iterate through gaps and check support
            for i, gap in enumerate(gaps):
                gap_size = gap[1] - gap[0]
                readsL = [L for L in gapsL.fetch(str(scaf.name)+'.gap.'+str(i+1)+'.L')]
                readsR = [R for R in gapsR.fetch(str(scaf.name)+'.gap.'+str(i+1)+'.R')]
                # Determine the number of supporting reads, store alignments in tuple
                support = [(L, R) for L, R in it.product(readsL, readsR) if L.query_name == R.query_name]
                if len(support) < args.min_reads:
                	continue
                # Iterate through supporting reads and measure wiggle
                fastq = list()
                for L, R in support:
                    read_span = R.query_alignment_start - L.query_alignment_end
                    if (gap_size - gap_size * args.wiggle) < read_span < (gap_size + gap_size * args.wiggle):
                        sequence = L.query_sequence[L.query_alignment_end:R.query_alignment_start]
                        quality = L.query_qualities[L.query_alignment_end:R.query_alignment_start]
                        fastq.append('@'+str(L.query_name)+'\n'+str(sequence)+'\n+\n'+str(quality)+'\n')
                # Continue if too many reads fail wiggle-check
                if len(fastq) < args.min_reads:
                    continue
                # Create sub-directory and write FastQ output
                gap_name = str(scaf.name)+'.gap.'+str(i+1)
                supported_gaps.append((gap_name, str(len(fastq))))
                path = 'Gap_Support/'+gap_name
                os.mkdir(path)
                with open(path+'/reads.fq', 'a') as output:
                    for read in fastq:
                        output.write(read)
        with open('Supported_Gaps.txt', 'w') as output:
            for gap_name, support in supported_gaps:
                output.write(gap_name+'\t'+support+'\n')
