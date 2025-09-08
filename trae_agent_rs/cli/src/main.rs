use clap::Parser;

#[derive(Parser)]
#[command(name = "trae-cli")]
#[command(version = "1.0")]
struct Cliconfig {
    #[arg(short=None, value_name="task")]
    task: String,

    #[arg(
        short = 'f',
        long = "file",
        help = "Path to a file containing the task description"
    )]
    file: String,

    #[arg(short = 'p', long = "provider", help = "LLM provider to use")]
    provider: String,

    #[arg(short = 'm', long = "model", help = "Specific model to use")]
    model: String,

    #[arg(long = "model-base-url", help = "Base URL for the model API")]
    model_base_url: String,
}

fn main() {
    let args = Cliconfig::parse();

    println!("task: {:?}, path: {:?}", args.task, args.file);
}
