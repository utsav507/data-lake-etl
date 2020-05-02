import configparser
from datetime import datetime
import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, col
from pyspark.sql.functions import year, month, dayofmonth, hour, weekofyear, date_format
from pyspark.sql.functions import monotonically_increasing_id
from pyspark.sql.types import StructType as R, StructField as Fld, DoubleType as Dbl, StringType as Str, IntegerType as Int, DateType as Dat, TimestampType as E
from pyspark.sql.functions import unix_timestamp, from_unixtime


config = configparser.ConfigParser()
config.read('dl.cfg')

os.environ['AWS_ACCESS_KEY_ID']=config['AWS_ACCESS_KEY_ID']
os.environ['AWS_SECRET_ACCESS_KEY']=config['AWS_SECRET_ACCESS_KEY']


def create_spark_session():
    """
        Create or retrieve a Spark Session
    """
    spark = SparkSession \
        .builder \
        .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:2.7.0") \
        .getOrCreate()
    return spark


def process_song_data(spark, input_data, output_data):
    """
        Description: This function loads song_data from S3 and processes it by extracting the
        songs and artist tables and then again loaded back to S3.
        
        Parameters:
            spark       : Spark Session
            input_data  : location of song_data json files with the songs metadata
            output_data : S3 bucket were dimensional tables in parquet format will be stored
    """
    
    # filepath to song data file
    song_data = input_data + 'song_data/A/A/*/*.json'
    
    # define schema
    songSchema = R([
        Fld("artist_id",Str()),
        Fld("artist_latitude",Dbl()),
        Fld("artist_location",Str()),
        Fld("artist_longitude",Dbl()),
        Fld("artist_name",Str()),
        Fld("duration",Dbl()),
        Fld("num_songs",Int()),
        Fld("title",Str()),
        Fld("year",Int()),
    ])
                      
    # read song data file
    df = spark.read.json(song_data, schema=songSchema)
    
    # definte song fields
    song_fields = ["title", "artist_id", "year", "duration"]
                      
    # extract columns to create songs table
    songs_table = df.select(song_fields).dropDuplicates().withColumn("song_id", monotonically_increasing_id())
    
    # write songs table to parquet files partitioned by year and artist
    songs_table.write.partitionBy("year", "artist_id").parquet(output_data + 'songs/')

    # define artist fields
    artists_fields = ["artist_id", "artist_name as name", "artist_location as location", "artist_latitude as latitude", "artist_longitude as longitude"]
                      
    # extract columns to create artists table
    artists_table = df.selectExpr(artists_fields).dropDuplicates()
    
    # write artists table to parquet files
    artists_table.write.parquet(output_data + 'artists/')

    
def process_log_data(spark, input_data, output_data):
    """
        Description: This function loads log_data from S3 and processes it by extracting the songs and artist tables
        and then again loaded back to S3. Also output from previous function is used in by spark.read.json command
        
        Parameters:
            spark       : Spark Session
            input_data  : location of log_data json files with the events data
            output_data : S3 bucket were dimensional tables in parquet format will be stored     
    """
                      
    # get filepath to log data file
    log_data = input_data + 'log_data/A/A/*.json'

    # read log data file
    df = spark.read.json(log_data)
    
    # filter by actions for song plays
    df = df.filter(df.page == 'NextSong')

    users_fields = ["userId as user_id", "firstName as first_name", "lastName as last_name", "gender", "level"]
    users_table = df.selectExpr(users_fields).dropDuplicates()

    users_table.write.parquet(output_data + 'users/')
    
    get_datetime = udf(date_format, TimestampType())
    df = df.withColumn("start_time", get_datetime('ts'))

    time_table = df.select("start_time").dropDuplicates() \
                .withColumn("hour", hour(col("start_time"))) \
                .withColumn("day", dayofmonth(col("start_time"))) \
                .withColumn("week", weekofyear(col("start_time"))) \
                .withColumn("month", month(col("start_time"))) \
                .withColumn("year", year(col("start_time"))) \
                .withColumn("weekday", date_format(col("start_time"), 'E'))
    
    time_table.write.partitionBy("year", "month").parquet(output_data + 'time/')
    
    df_songs = spark.read.parquet(output_data + 'songs/*/*/*')

    df_artists = spark.read.parquet(output_data + 'artists/*')

    songs_logs = df.join(songs_df, (df.song == songs_df.title))
    artists_songs_logs = songs_logs.join(df_artists, (songs_logs.artist == df_artists.name))

    songplays = artists_songs_logs.join(
        time_table,
        artists_songs_logs.ts == time_table.start_time, 'left'
    ).drop(artists_songs_logs.year)         
                      
    # extract columns from joined song and log datasets to create songplays table 
    songplays_table = songplays.select(
        col('start_time').alias('start_time'),
        col('userId').alias('user_id'),
        col('level').alias('level'),
        col('song_id').alias('song_id'),
        col('artist_id').alias('artist_id'),
        col('sessionId').alias('session_id'),
        col('location').alias('location'),
        col('userAgent').alias('user_agent'),
        col('year').alias('year'),
        col('month').alias('month'),
    ).repartition("year", "month")

    # write songplays table to parquet files partitioned by year and month
    songplays_table.write.partitionBy("year", "month").parquet(output_data + 'songplays/')    
    
    
def main():
    """
        Extract songs and events data from S3, Transform it into dimensional tables format, and Load it back to S3 in Parquet format
    """
    spark = create_spark_session()
    input_data = "s3a://udacity-dend/"
    output_data = "s3a://sparkify-data-lake-dend/"
    
    process_song_data(spark, input_data, output_data)    
    process_log_data(spark, input_data, output_data)


if __name__ == "__main__":
    main()