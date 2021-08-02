

import multiprocessing as mp
from multiprocessing import Manager
from functools import wraps

import pandas as pd
from neo4j import GraphDatabase
import csv
import glob
import logging
import yaml
import datetime
import sys, os
import time


def timer(func):
    """Print the runtime of the decorated function"""
    @wraps(func)
    def wrapper_timer(*args, **kwargs):
        print(f"args len:{len(args)}")

        start_time = time.perf_counter()    # 1
        value = func(*args, **kwargs)
        print()
        end_time = time.perf_counter()      # 2
        run_time = end_time - start_time    # 3
        try:
            doc_string=args[0]
        except:
            doc_string="'NO ARGS'"
        logging.info(f"Finished {func.__name__!r} with {doc_string} in {run_time:.4f} secs.")
        try:
            namespace=args[2]
            metrics=namespace.metrics_df
            namespace.metrics_df=metrics.append({"function_name":f"{func.__name__!r}","step_name":doc_string,"time_in_seconds":f"{run_time:.4f}"}, ignore_index=True)
        except:
            print(f"No args to write the shared data.")
        return value
    return wrapper_timer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)

config_file="./config.yml"
    

def db_connector(func):
    @wraps(func)
    def neo_connection(*args,**kwargs):
        
        try:
            config = load_config()
            neo_driver = GraphDatabase.driver(config['server_uri'], auth=(config['admin_user'], config['admin_pass']),encrypted=False)
            kwargs['neo_driver'] = neo_driver
            kwargs['config'] = config
            rv = func(*args,**kwargs)
            
        except Exception as e:
            print("Database connection error {0}".format(e))
            
        finally:
            neo_driver.close()
            return rv
        
    return neo_connection


@timer
@db_connector
def run_cypher(doc_string,queries,ns,neo_driver=None,config=None):
    """
    Run raw cypher queries.
    """
    
    if type(queries)==list:
        # print("Processing List of Queries")
        with neo_driver.session(database="legand") as session:
            for query in queries:
                # print(f"\n **** Running \n {query}")
                try:
                    session.run(query)
                except Exception as e:
                    logging.error(e)
    else:
        with neo_driver.session(database="legand") as session:
            # print("Processing Single Query")
            # print(f"\n **** Running \n {queries}")
            try:
                result=session.run(queries)
            except Exception as e:
                logging.error(e)
            return result

def task_submit(tasks, pool=None):
        
        if (pool):
            logging.info('Running with parallel')
            results_pool = [pool.apply_async(function_submit,task) for task in tasks]
            output = [p.get() for p in results_pool]
        else:
            logging.info('Running with sequential')
            result = [function_submit(task[0],*task[1:]) for task in tasks]

def function_submit(func,*args):
#     logging.info('Started Task : '.format({func.__name__})   )
    result = func(*args)

def load_config(configuration=config_file):
    """
    Read config file from sys args and load configurations.
    """
    with open(configuration) as config_file:
        config = yaml.load(config_file)
    return config

def get_files_list(basefolder,folder_name,extention):
    print('Getting Files from ',basefolder,'/',folder_name,' with extenstion ',extention)
    return glob.glob("{0}/{1}/*.{2}".format(basefolder,folder_name,extention))

@timer
def main():
    mgr = Manager()
    ns = mgr.Namespace()
    # metrics_df=pd.DataFrame()
    ns.metrics_df = pd.DataFrame()

    try:
        metrics_output_file_name=sys.argv[1]
    except:
        metrics_output_file_name="run_time_metrics.csv"

    config = load_config()
    process_type=config['parallel']
    tasks = config['queries'].keys()
    num_processors = 10 #mp.cpu_count()
    no_of_tasks=len(tasks)
    times_to_run=config['times_to_run']
    
    if process_type:
        exec_tasks=list(tasks)*times_to_run
        prep_tasks = [[run_cypher,task,config['queries'][task]['cql'],ns] for task in exec_tasks ]
        if len(prep_tasks)>0:
            with mp.Pool(num_processors) as pool:
                task_submit(prep_tasks,pool)

    else:
        print(f"Running tasks in sequential order.")
        exec_tasks = [task for task in tasks for i in range(0,times_to_run)  ]
        prep_tasks = [[run_cypher,task,config['queries'][task]['cql'],ns] for task in exec_tasks ]
        task_submit(prep_tasks)
    metrics_df=ns.metrics_df
    metrics_df.to_csv(metrics_output_file_name, index=False)
    return



if __name__ == "__main__":

    main()
