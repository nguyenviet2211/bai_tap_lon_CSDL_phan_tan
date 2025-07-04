#!/usr/bin/python2.7
#
# Interface for the assignement
#

import psycopg2

DATABASE_NAME = 'dds_assgn1'

def getopenconnection(user='postgres', password='1234', dbname='postgres'):
    return psycopg2.connect("dbname='" + dbname + "' user='" + user + "' host='localhost' password='" + password + "'")

def loadratings(ratingstablename, ratingsfilepath, openconnection):
    """
    Function to load data in @ratingsfilepath file to a table called @ratingstablename.
    """
    create_db(DATABASE_NAME)
    con = openconnection
    cur = con.cursor()
    cur.execute("DROP TABLE IF EXISTS " + ratingstablename + ";")
    cur.execute("create table " + ratingstablename + "(userid integer, extra1 char, movieid integer, extra2 char, rating float, extra3 char, timestamp bigint);")
    cur.copy_from(open(ratingsfilepath),ratingstablename,sep=':')
    cur.execute("alter table " + ratingstablename + " drop column extra1, drop column extra2, drop column extra3, drop column timestamp;")
    cur.close()
    con.commit()

def rangepartition(ratingstablename, numberofpartitions, openconnection):
    """
    Function to create partitions of main table based on range of ratings.
    """
    con = openconnection
    cur = con.cursor()
    delta = 5 / numberofpartitions
    RANGE_TABLE_PREFIX = 'range_part'
    for i in range(0, numberofpartitions):
        minRange = i * delta
        maxRange = minRange + delta
        table_name = RANGE_TABLE_PREFIX + str(i)
        cur.execute("create table " + table_name + " (userid integer, movieid integer, rating float);")
        if i == 0:
            cur.execute("insert into " + table_name + " (userid, movieid, rating) select userid, movieid, rating from " + ratingstablename + " where rating >= " + str(minRange) + " and rating <= " + str(maxRange) + ";")
        else:
            cur.execute("insert into " + table_name + " (userid, movieid, rating) select userid, movieid, rating from " + ratingstablename + " where rating > " + str(minRange) + " and rating <= " + str(maxRange) + ";")
    cur.close()
    con.commit()

def roundrobinpartition(ratingstablename, numberofpartitions, openconnection):
    """
    Partition the table using round robin
    """
    con = openconnection
    cur = con.cursor()
    RROBIN_TABLE_PREFIX = 'rrobin_part'

    
    cur.execute("DROP TABLE IF EXISTS roundrobin_metadata;")
    cur.execute("CREATE TABLE roundrobin_metadata (next_insert_partition INT);")
    cur.execute("INSERT INTO roundrobin_metadata VALUES (0);")

    
    for i in range(numberofpartitions):
        cur.execute(f"DROP TABLE IF EXISTS {RROBIN_TABLE_PREFIX}{i};")
        cur.execute(f"CREATE TABLE {RROBIN_TABLE_PREFIX}{i} (userid INTEGER, movieid INTEGER, rating FLOAT);")

    cur.execute(f"""
        WITH numbered AS (
            SELECT userid, movieid, rating, ROW_NUMBER() OVER () as rn FROM {ratingstablename}
        )
        SELECT * INTO TEMP temp_rr FROM numbered;
    """)
    
    for i in range(numberofpartitions):
        cur.execute(f"""
            INSERT INTO {RROBIN_TABLE_PREFIX}{i}(userid, movieid, rating)
            SELECT userid, movieid, rating FROM temp_rr WHERE MOD(rn - 1, {numberofpartitions}) = {i};
        """)
    
    cur.execute("DROP TABLE temp_rr;")
    cur.close()
    con.commit()


def roundrobininsert(ratingstablename, userid, itemid, rating, openconnection):
    """
    Insert a new row into the main table and specific round robin partition based on metadata.
    """
    con = openconnection
    cur = con.cursor()
    RROBIN_TABLE_PREFIX = 'rrobin_part'

 
    cur.execute("INSERT INTO " + ratingstablename + "(userid, movieid, rating) VALUES (%s, %s, %s);", (userid, itemid, rating))


    cur.execute("SELECT next_insert_partition FROM roundrobin_metadata;")
    current_index = cur.fetchone()[0]

    numberofpartitions = count_partitions(RROBIN_TABLE_PREFIX, openconnection)

    table_name = RROBIN_TABLE_PREFIX + str(current_index)
    cur.execute("INSERT INTO " + table_name + "(userid, movieid, rating) VALUES (%s, %s, %s);", (userid, itemid, rating))

    next_index = (current_index + 1) % numberofpartitions
    cur.execute("UPDATE roundrobin_metadata SET next_insert_partition = %s;", (next_index,))

    cur.close()
    con.commit()


def rangeinsert(ratingstablename, userid, itemid, rating, openconnection):
    """
    Function to insert a new row into the main table and specific partition based on range rating.
    """
    con = openconnection
    cur = con.cursor()
    RANGE_TABLE_PREFIX = 'range_part'
    numberofpartitions = count_partitions(RANGE_TABLE_PREFIX, openconnection)
    delta = 5 / numberofpartitions
    index = int(rating / delta)
    if rating % delta == 0 and index != 0:
        index = index - 1
    table_name = RANGE_TABLE_PREFIX + str(index)
    cur.execute("INSERT INTO " + ratingstablename + "(userid, movieid, rating) values (" + str(userid) + "," + str(itemid) + "," + str(rating) + ");")
    cur.execute("insert into " + table_name + "(userid, movieid, rating) values (" + str(userid) + "," + str(itemid) + "," + str(rating) + ");")
    cur.close()
    con.commit()

def create_db(dbname):
    """
    We create a DB by connecting to the default user and database of Postgres
    The function first checks if an existing database exists for a given name, else creates it.
    :return:None
    """
    # Connect to the default database
    con = getopenconnection(dbname='postgres')
    con.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = con.cursor()

    # Check if an existing database with the same name exists
    cur.execute('SELECT COUNT(*) FROM pg_catalog.pg_database WHERE datname=\'%s\'' % (dbname,))
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute('CREATE DATABASE %s' % (dbname,))  # Create the database
    else:
        print('A database named {0} already exists'.format(dbname))

    # Clean up
    cur.close()
    con.close()

def count_partitions(prefix, openconnection):
    """
    Function to count the number of tables which have the @prefix in their name somewhere.
    """
    con = openconnection
    cur = con.cursor()
    cur.execute("select count(*) from pg_stat_user_tables where relname like " + "'" + prefix + "%';")
    count = cur.fetchone()[0]
    cur.close()

    return count
