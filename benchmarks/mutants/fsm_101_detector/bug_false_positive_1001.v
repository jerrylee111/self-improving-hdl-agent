module top_module(input clk, input reset, input bit_in, output reg found);
    reg [2:0] hist;

    always @(posedge clk) begin
        if (reset) begin
            hist <= 3'b000;
            found <= 1'b0;
        end else begin
            hist <= {hist[1:0], bit_in};
            found <= ({hist[1:0], bit_in} == 3'b101) || ({hist[1:0], bit_in} == 3'b001);
        end
    end
endmodule
