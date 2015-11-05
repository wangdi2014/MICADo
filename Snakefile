import random
rule all:
    input:expand("data/synthetic/C_FOOFOO_{seed}_{nreads}_{frac}_{nalt}_1-1-1.combined_alterations.json",\
                seed=random.sample(range(10000),k=1),\
                nreads=[150,500,1000],\
                nalt=[1,2,3],\
                alt_type=['1-1-1','1-1-0','0-1-1'],\
                frac=["03","05","10","30","50"])


rule clean:
    shell:"""
        rm data/synthetic/*.json
        rm data/synthetic/*.fastq
        rm data/synthetic/*.bam
        rm data/synthetic/*.sam
        rm data/synthetic/*.bai
    """

rule run_micado:
    input : fasta_ref="data/reference/reference_TP53.fasta",\
            random_sample="data/synthetic/{sample}.fastq",\
            snp_data="data/reference/snp_TP53.tab"
    params : sample_name= "data/synthetic/{sample}"
    output:
            micado_results=temp("data/synthetic/{sample}.significant_alterations.json"),\

    shell:"""
        source ~/.virtualenvs/micado/bin/activate
        export PYTHONPATH=`pwd`/src

        # run micado
        python src/principal.py --fastq {input.random_sample} --experiment TP53 \
                                --fasta {input.fasta_ref} \
                                --samplekey synth2 \
                                --snp {input.snp_data} \
                                --npermutations 20 --pvalue 0.1 \
                                --results {output.micado_results}


"""


rule generate_sample:
    input:input_sam="data/alignments/C_model_GMAPno40_NM_000546.5.sam"
    params:
            sample_name="data/synthetic/{sample}_{seed}_{nreads}_{frac}_{nalt}_{altw}"

    output:random_alt=temp("data/synthetic/{sample}_{seed,\d+}_{nreads,\d+}_{frac,\d+}_{nalt,\d+}_{altw}.fastq"),
           non_alt=temp("data/synthetic/{sample}_{seed,\d+}_{nreads,\d+}_{frac,\d+}_{nalt,\d+}_{altw}_non_alt.fastq"),\
           sampler_results=temp("data/synthetic/{sample}_{seed,\d+}_{nreads,\d+}_{frac,\d+}_{nalt,\d+}_{altw}.alterations.json")
    shell:"""
        source ~/.virtualenvs/micado/bin/activate
        export PYTHONPATH=`pwd`/src

        # build a sample
        python src/read_sampler/altered_reads_sampler.py --input_sam {input.input_sam}  \
                    --output_file_prefix "{params.sample_name}" \
                    --n_reads {wildcards.nreads} --fraction_altered 0.{wildcards.frac} --n_alterations {wildcards.nalt} --alt_weight {wildcards.altw} \
                    --seed {wildcards.seed} \
                    --systematic_offset -202

    """
rule combine_json :
    input : micado_results="data/synthetic/{sample}.significant_alterations.json",\
            sampler_results="data/synthetic/{sample}.alterations.json"

    output:combined_json=temp("data/synthetic/{sample}.combined_alterations.temp.json"),
           cleaned_json="data/synthetic/{sample}.combined_alterations.json"
    shell:"""
        # merge known alterations and identified alterations
        source ~/.virtualenvs/micado/bin/activate
        export PYTHONPATH=`pwd`/src
        bin/merge_json_objects.py {input.sampler_results} {input.micado_results} > {output.combined_json}
        jq "." < {output.combined_json} > {output.cleaned_json}

    """

rule align_synthetic_data:
    input: fastq="data/synthetic/{sample}.fastq"
    params: TGTGENOME="NM_000546.5",sample="data/synthetic/{sample}"
    output: "data/synthetic/{sample}_C_model_GMAPno40.sorted.bam"
    shell:"""
        gmap --min-intronlength=15000 -t 32 -D data/gmap_genomes/{params.TGTGENOME} \
             -d {params.TGTGENOME} -f samse --read-group-id=EORTC10994 \
             --read-group-name=GemSim_test --read-group-library=MWG1 \
             --read-group-platform=PACBIO {input.fastq} >  {params.sample}_C_model_GMAPno40.sam

        samtools view -b -S {params.sample}_C_model_GMAPno40.sam > {params.sample}_C_model_GMAPno40.bam
        samtools sort {params.sample}_C_model_GMAPno40.bam {params.sample}_C_model_GMAPno40.sorted
        samtools index {params.sample}_C_model_GMAPno40.sorted.bam
    """
