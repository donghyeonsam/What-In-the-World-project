FROM apache/kafka:4.3.1

USER root

ADD https://github.com/prometheus/jmx_exporter/releases/download/1.6.0/jmx_prometheus_javaagent-1.6.0.jar /opt/news-monitoring/jmx_prometheus_javaagent.jar
COPY jmx-exporter.yml /opt/news-monitoring/jmx-exporter.yml

EXPOSE 7071
