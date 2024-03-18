# Import modules
import os
import argparse

# Driver functions for the profiler module
class AGI:
    def __init__(self, args):
        self.args = args
    def profile(self):
        from AGI.utils.utils import checkDCGMImports
        from AGI.io.MetricsDataIO import MetricsDataIO
        
        # Check if DCGM bindings are available before importing AGI modules
        # This raises an exception if DCGM is not available
        checkDCGMImports()
        # Import AGI modules
        from AGI.profiler.GPUMetricsProfiler import GPUMetricsProfiler
        
        # Check if job was called via SLURM
        # We need this in order to extract information regarding which GPUs to monitor from the environment
        try:
            jobId = os.environ['SLURM_JOB_ID']
            # Assume exactly one GPU per rank for now
            # It is important to set --gpus-per-task=1 in the SLURM script for this to work
            gpuIds = [int(gpu) for gpu in os.environ['SLURM_STEP_GPUS'].strip().split(',')]
        except KeyError:
            # Hack - if --gpus-per-task=1 is not set, we can still use SLURM_PROCID mod 4 to determine the GPU ID
            print("WARNING: SLURM environment variables not found. Using SLURM_PROCID mod 4 to determine GPU ID.")
            jobId = os.environ['SLURM_JOB_ID']
            procId = int(os.environ['SLURM_PROCID'])
            gpuIds = [procId%4]

        # Set default output file if not specified
        if self.args.output_file is None:
            self.args.output_file = f"AGI_{jobId}.sqlite"
            
        # Create profiler object
        profiler = GPUMetricsProfiler(
            gpuIds=gpuIds, # Need to pass a list of GPU IDs
            samplingTime=self.args.sampling_time,
            label=self.args.label,
            maxRuntime=self.args.max_runtime,
        )

        # Run workload
        profiler.run(self.args.wrap)

        # Get collected metrics
        metadata, data = profiler.getCollectedData()

        # We force delete the profiler object to ensure that the DCGM context is destroyed
        # We do not want to keep the DCGM context open for the entire lifetime of the profiler
        # Doing so results in strange and unpredictable crashes
        del profiler

        # Create IO handler
        ifExists = "fail"
        if self.args.append:
            ifExists = "append"
        elif self.args.force_overwrite:
            ifExists = "overwrite"

        IO = MetricsDataIO(self.args.output_file, readOnly=False, ifExists=ifExists)

        # Dump data to SQL DB
        IO.dump(metadata, data)
        
        return 0

    # Driver function for the analyze module
    def analyze(self):
        from AGI.analysis.analysis import GPUMetricsAnalyzer
        
        # Instantiate analyzer class
        analyzer = GPUMetricsAnalyzer(
            inputFile=self.args.input_file,
            detectOutliers=self.args.detect_outliers
            )

        # Print GPU information
        if self.args.show_metadata:
            analyzer.showMetadata()

        # Print summary of metricsx
        if self.args.no_summary == False:
            analyzer.summary(self.args.verbosity)
        
        # Plot time-series of metrics
        if self.args.plot_time_series:
            analyzer.plotTimeSeries()

        # Plot load-balancing of metrics
        if self.args.plot_load_balancing:
            #print("Usage map plotting is temporarily disabled due to restructuring of the code.")
            analyzer.plotUsageMap()
        
        return 0

if __name__ == '__main__':
    # Main parser
    parser = argparse.ArgumentParser(description='Monitor and analyze resource usage of a workload with AGI')

    # Subparsers
    subparsers = parser.add_subparsers(dest='subcommand', help='sub-command help')

    # Profile subcommand
    parser_profile = subparsers.add_parser('profile', help='Profile command help')
    parser_profile.add_argument('--wrap', '-w', metavar='wrap', type=str, nargs='+', help='Wrapped command to run', required=True)
    parser_profile.add_argument('--label', '-l', metavar='label', type=str, help='Workload label.', required=False)
    parser_profile.add_argument('--max-runtime', '-m', metavar='max-runtime', type=int, default=600, help='Maximum runtime of the wrapped command in seconds')
    parser_profile.add_argument('--sampling-time', '-t', metavar='sampling-time', type=int, default=500, help='Sampling time of GPU metrics in milliseconds')
    parser_profile.add_argument('--verbose', '-v', action='store_true', help='Print verbose GPU metrics to stdout')
    parser_profile.add_argument('--force-overwrite', '-f', action='store_true', help='Force overwrite of output file', default=False)
    parser_profile.add_argument('--append', '-a', action='store_true', help='Append profiling data to the output file', default=False)
    parser_profile.add_argument('--output-file', '-o', metavar='output-file', type=str, default=None, help='Output SQL file for collected GPU metrics', required=True)

    # Analyze subcommand
    parser_analyze = subparsers.add_parser('analyze', help='Analyze command help')
    parser_analyze.add_argument('--input-file', '-i', type=str, required=True, help='Input file for analysis')
    parser_analyze.add_argument('--no-summary', '-ns', action="store_true", default=False, help='Hide summary of metrics.')
    parser_analyze.add_argument('--show-metadata', '-mtd', action='store_true',  default=False, help='Generate metadata for the input SQL file.')
    parser_analyze.add_argument('--verbosity', '-v', type=str, help='Set verbosity of the summary. Default is "medium".', choices=['low', 'medium', 'high'], default='medium')
    parser_analyze.add_argument('--detect-outliers', '-d', type=str, default='none', choices=['leading', 'trailing', 'none', 'all'],
                                help='Heuristically detect outlier samples and discard them from the analysis')
    parser_analyze.add_argument('--auto-diagnose', '-ad', type=bool, help='Print summary of metrics. Default is True.')
    parser_analyze.add_argument('--plot-time-series', '-pts', action='store_true', help='Generate time-series plots of metrics.')
    parser_analyze.add_argument('--plot-load-balancing', '-plb', action='store_true', help='Generate load-balancing plots of metrics.')

    # Parse arguments
    args = parser.parse_args()

    # Run appropriate command
    AGIObj = AGI(args)
    if args.subcommand == 'profile':
        AGIObj.profile() 
    elif args.subcommand == 'analyze':
        AGIObj.analyze()
    else:
        # Print help if no subcommand is given
        parser.print_help()
