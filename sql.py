import os
import psycopg2
import psycopg2.extras
import tabulate
from dotenv import load_dotenv
sample_query = """
SELECT 
    cust,
    (SELECT SUM(s1.quant) 
     FROM sales s1 
     WHERE s1.cust = s.cust AND s1.state = 'NY') AS sum_x_quant,

    (SELECT SUM(s2.quant) 
     FROM sales s2 
     WHERE s2.cust = s.cust AND s2.state = 'NJ') AS sum_y_quant,

    (SELECT SUM(s3.quant) 
     FROM sales s3 
     WHERE s3.cust = s.cust AND s3.state = 'CT') AS sum_z_quant

FROM sales s
GROUP BY cust
HAVING 
    (SELECT SUM(s1.quant) 
     FROM sales s1 
     WHERE s1.cust = s.cust AND s1.state = 'NY') > 2 * 
    (SELECT SUM(s2.quant) 
     FROM sales s2 
     WHERE s2.cust = s.cust AND s2.state = 'NJ')
    
    OR

    (SELECT AVG(s1.quant) 
     FROM sales s1 
     WHERE s1.cust = s.cust AND s1.state = 'NY') >
    (SELECT AVG(s3.quant) 
     FROM sales s3 
     WHERE s3.cust = s.cust AND s3.state = 'CT');
"""

def query():
    """
    Used for testing standard queries in SQL.
    """
    load_dotenv()

    user = os.getenv('USER')
    password = os.getenv('PASSWORD')
    dbname = os.getenv('DBNAME')

    conn = psycopg2.connect("dbname="+dbname+" user="+user+" password="+password,
                            cursor_factory=psycopg2.extras.DictCursor)
    cur = conn.cursor()
    cur.execute(sample_query)

    return tabulate.tabulate(cur.fetchall(),
                             headers="keys", tablefmt="psql")


def main():
    print(query())


if "__main__" == __name__:
    main()
